"""Mutation-driven tests for import_manager's manifest/bootstrap parser.

This is the externally-supplied-data boundary: cache manifests and archives
come from the server and must be validated before anything touches the user's
collection.

Covers:
- ``_subscription_from_manifest``: missing URL, download failure, missing
  deck path, missing deck data in archive, unsupported compression, invalid
  JSON, and the happy path.
- ``_resolve_cache_bootstrap_entries``: non-list passthrough, non-bootstrap
  passthrough, malformed entry, valid resolution, error propagation.
"""

import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest
import requests

from import_manager import (
    CacheBootstrapError,
    _resolve_cache_bootstrap_entries,
    _subscription_from_manifest,
)


def _make_archive(deck_json, path="deck.json"):
    """Build an in-memory zip archive containing the deck JSON at ``path``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(path, json.dumps(deck_json).encode("utf-8"))
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content=b"", content_length=None):
        self._content = content
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=1024):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]

    def close(self):
        pass


# ──────────────────────────────────────────────────────────────────────
# _subscription_from_manifest
# ──────────────────────────────────────────────────────────────────────


class TestSubscriptionFromManifest:
    def test_missing_archive_url(self, mw_mock):
        with pytest.raises(CacheBootstrapError, match="missing archive URL"):
            _subscription_from_manifest("hash1", {}, None)

    def test_download_failure(self, mw_mock):
        with patch(
            "import_manager.requests.get",
            side_effect=requests.RequestException("boom"),
        ):
            with pytest.raises(CacheBootstrapError, match="Unable to download"):
                _subscription_from_manifest("hash1", {}, "http://x/archive.zip")

    def test_missing_deck_path(self, mw_mock):
        archive = _make_archive({"deck": {"name": "D"}})
        with patch("import_manager.requests.get", return_value=_FakeResponse(archive)):
            manifest = {"deck_data": {}, "media": {}}
            with pytest.raises(CacheBootstrapError, match="missing deck data path"):
                _subscription_from_manifest("hash1", manifest, "http://x/a.zip")

    def test_deck_data_missing_in_archive(self, mw_mock):
        archive = _make_archive({"deck": {"name": "D"}}, path="other.json")
        with patch("import_manager.requests.get", return_value=_FakeResponse(archive)):
            manifest = {"deck_data": {"path": "deck.json"}, "media": {}}
            with pytest.raises(CacheBootstrapError, match="not present in cache"):
                _subscription_from_manifest("hash1", manifest, "http://x/a.zip")

    def test_unsupported_compression(self, mw_mock):
        archive = _make_archive({"deck": {"name": "D"}})
        with patch("import_manager.requests.get", return_value=_FakeResponse(archive)):
            manifest = {
                "deck_data": {"path": "deck.json", "compression": "bz2"},
                "media": {},
            }
            with pytest.raises(
                CacheBootstrapError, match="Unsupported deck compression"
            ):
                _subscription_from_manifest("hash1", manifest, "http://x/a.zip")

    def test_invalid_deck_json(self, mw_mock):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("deck.json", b"not json{")
        with patch(
            "import_manager.requests.get", return_value=_FakeResponse(buf.getvalue())
        ):
            manifest = {"deck_data": {"path": "deck.json"}, "media": {}}
            with pytest.raises(CacheBootstrapError, match="not valid JSON"):
                _subscription_from_manifest("hash1", manifest, "http://x/a.zip")

    def test_happy_path(self, mw_mock):
        deck_payload = {"deck": {"name": "Test", "crowdanki_uuid": "d1"}, "meta": {}}
        archive = _make_archive(deck_payload)
        with patch("import_manager.requests.get", return_value=_FakeResponse(archive)):
            manifest = {
                "deck_data": {"path": "deck.json"},
                "media": {},
                "source_last_update": "2025-01-01",
            }
            sub = _subscription_from_manifest("hash1", manifest, "http://x/a.zip")
        assert sub["deck"]["name"] == "Test"
        assert sub["deck_last_modified"] == "2025-01-01"

    def test_cancel_during_download(self, mw_mock):
        """User cancel mid-download aborts with OperationAbortedError."""
        archive = _make_archive({"deck": {"name": "D"}})

        class _CancellingResponse(_FakeResponse):
            def iter_content(self, chunk_size=1024):
                yield self._content[:4]
                # want_cancel becomes True after the first chunk
                yield b""

        mw_mock.progress.want_cancel.return_value = True
        with patch(
            "import_manager.requests.get", return_value=_CancellingResponse(archive)
        ):
            from utils import OperationAbortedError

            with pytest.raises(OperationAbortedError):
                _subscription_from_manifest(
                    "hash1", {"deck_data": {}, "media": {}}, "http://x/a.zip"
                )


# ──────────────────────────────────────────────────────────────────────
# _resolve_cache_bootstrap_entries
# ──────────────────────────────────────────────────────────────────────


class TestResolveCacheBootstrapEntries:
    def test_non_list_returns_as_is(self):
        assert _resolve_cache_bootstrap_entries("not-a-list") == "not-a-list"

    def test_non_bootstrap_entries_passthrough(self):
        entries = [{"mode": "normal", "deck": {}}, "plain"]
        assert _resolve_cache_bootstrap_entries(entries) == entries

    def test_malformed_entry_raises(self):
        entries = [{"mode": "cache-bootstrap", "deck_hash": "h1"}]  # no manifest
        with pytest.raises(CacheBootstrapError, match="Malformed cache bootstrap"):
            _resolve_cache_bootstrap_entries(entries)

    def test_valid_entry_resolved(self):
        entry = {
            "mode": "cache-bootstrap",
            "deck_hash": "h1",
            "manifest": {"manifest_presigned_url": "http://x/manifest.json"},
        }
        with (
            patch(
                "import_manager._fetch_manifest", return_value={"deck_data": {}}
            ) as m_fetch,
            patch(
                "import_manager._subscription_from_manifest",
                return_value={"deck": {"name": "Resolved"}},
            ) as m_sub,
        ):
            result = _resolve_cache_bootstrap_entries([entry])
        assert result == [{"deck": {"name": "Resolved"}}]
        m_fetch.assert_called_once_with("http://x/manifest.json")
        m_sub.assert_called_once()

    def test_bootstrap_error_propagates(self):
        entry = {
            "mode": "cache-bootstrap",
            "deck_hash": "h1",
            "manifest": {"manifest_presigned_url": "http://x/manifest.json"},
        }
        with patch(
            "import_manager._fetch_manifest",
            side_effect=CacheBootstrapError("broken"),
        ):
            with pytest.raises(CacheBootstrapError, match="broken"):
                _resolve_cache_bootstrap_entries([entry])
