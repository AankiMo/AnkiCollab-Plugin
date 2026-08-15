"""Cancellation & failure-injection tests (Phase 3.5).

For export and import, a failure or cancellation at an external boundary must
never leave a partially-corrupted collection state behind, must propagate (or
handle) the correct exception type, and must not retry after an explicit user
cancellation.  These tests assert the *safe end state*, not merely that an
exception was raised.
"""

import requests
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.integration

import utils as utils_mod
from utils import (
    OperationAbortedError,
    check_collection_or_abort,
)
from import_manager import CacheBootstrapError, _fetch_manifest
from export_manager import (
    _apply_media_reference_updates,
    _handle_operation_aborted,
    _on_suggest_deck_prepared,
    _prepare_deck_for_suggestion,
    get_server_missing_media,
)


class TestImportFailures:
    def test_manifest_network_error_raises_cache_bootstrap_error(self):
        with patch("import_manager.requests.get", side_effect=requests.ConnectionError):
            with pytest.raises(CacheBootstrapError) as excinfo:
                _fetch_manifest("http://example.com/manifest")
        assert "Unable to download cache manifest" in str(excinfo.value)

    def test_manifest_malformed_json_raises_cache_bootstrap_error(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("bad json")
        with patch("import_manager.requests.get", return_value=resp):
            with pytest.raises(CacheBootstrapError) as excinfo:
                _fetch_manifest("http://example.com/manifest")
        assert "not valid JSON" in str(excinfo.value)


class TestExportFailures:
    def test_media_missing_network_failure_returns_empty_safely(self):
        """A network error fetching missing media must not raise or corrupt
        state — it returns an empty list so the workflow can continue safely."""
        from api_client import api_client

        with patch.object(
            api_client, "get", side_effect=requests.ConnectionError("down")
        ):
            deck_hash, missing = get_server_missing_media("deck-hash")
        assert deck_hash == "deck-hash"
        assert missing == []

    def test_operation_aborted_is_handled_not_retried(self):
        # OperationAbortedError is a graceful-cancel signal: handled → True
        assert (
            _handle_operation_aborted(
                OperationAbortedError("closed", phase="Export"), "Export"
            )
            is True
        )
        # Any other exception is NOT treated as a graceful cancel
        assert _handle_operation_aborted(RuntimeError("boom"), "Export") is False


class TestCollectionUnavailable:
    def test_check_collection_or_abort_raises_operation_aborted(self, monkeypatch):
        monkeypatch.setattr(utils_mod, "mw", MagicMock(col=None))
        with pytest.raises(OperationAbortedError) as excinfo:
            check_collection_or_abort("test_phase")
        assert excinfo.value.phase == "test_phase"

    def test_prepare_deck_aborts_when_collection_closed(self, monkeypatch):
        """Collection closing mid-export aborts with OperationAbortedError and
        performs no further work (no partial state)."""
        monkeypatch.setattr(utils_mod, "mw", MagicMock(col=None))
        with patch("export_manager.deck_initializer.from_collection") as mock_from:
            with pytest.raises(OperationAbortedError):
                _prepare_deck_for_suggestion(1, [1], "hash")
        # No representation work was attempted
        mock_from.assert_not_called()

    def test_apply_media_updates_noop_when_collection_unavailable(
        self, mw_mock, monkeypatch
    ):
        """If the collection disappears mid-update, no note is written."""
        update_notes = mw_mock.col.update_notes  # capture before nulling col
        no_col = MagicMock(col=None)
        monkeypatch.setattr(utils_mod, "mw", no_col)
        monkeypatch.setattr("export_manager.mw", no_col)
        results = {
            "updates": [{"note_id": 1, "mod": 0, "fields": ["x"], "old_filenames": []}],
            "filename_mapping": {},
        }
        count, opchanges = _apply_media_reference_updates(results)
        assert count == 0
        assert opchanges is None
        update_notes.assert_not_called()


class TestUserCancellation:
    def test_suggestion_cancelled_by_user_does_not_retry(self, mw_mock):
        """When the user cancels the commit-info dialog, no upload/QueryOp
        may be scheduled — a retry would send data the user declined to send."""
        deck_repr = MagicMock()
        with (
            patch("export_manager.get_maintainer_data", return_value=("token", False)),
            patch("export_manager.get_commit_info", return_value=None),
            patch("export_manager.QueryOp") as mock_queryop,
            patch("export_manager.aqt.utils.tooltip") as mock_tooltip,
        ):
            _on_suggest_deck_prepared((deck_repr, []), 1, "hash", 1, None)

        mock_queryop.assert_not_called()
        mock_tooltip.assert_called_once()
