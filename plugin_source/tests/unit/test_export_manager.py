"""Tests for export_manager.py — regex patterns, media validation, helpers."""

import os
import pytest
from unittest.mock import MagicMock, patch

from export_manager import (
    COMPILED_SOUND_REGEXES,
    COMPILED_HTML_MEDIA_REGEXES,
    ALL_COMPILED_MEDIA_REGEXES,
    _is_valid_media_file,
    _filter_valid_filename_mapping,
    _apply_media_reference_updates,
    schedule_media_reference_updates,
    _handle_operation_aborted,
    ASYNC_MEDIA_REF_THRESHOLD,
    BATCH_UPDATE_NOTES_SIZE,
)
from utils import OperationAbortedError

# ──────────────────────────────────────────────────────────────────────
# Constants → behavior at the boundaries (not tautological `> 0` checks)
# ──────────────────────────────────────────────────────────────────────


class TestBatchUpdateNotesSize:
    """BATCH_UPDATE_NOTES_SIZE controls the batch size for mw.col.update_notes.

    Construct exactly N-1 / N / N+1 notes-to-save and assert the batching loop
    produces the correct number of batches and batch sizes at each boundary.
    """

    @pytest.fixture
    def media_dir(self, tmp_path):
        d = tmp_path / "media"
        d.mkdir()
        (d / "new.mp3").write_bytes(b"x" * 100)  # valid (>= 100 bytes)
        return d

    def _make_updates(self, n):
        return [
            {
                "note_id": i,
                "note_guid": f"guid_{i}",
                "fields": [f"front {i}", "back"],
                "old_fields": ["front", "back"],
                "mod": 1234,
                "old_filenames": ["old.mp3"],
            }
            for i in range(n)
        ]

    def _run(self, mw_mock, n, media_dir):
        results = {
            "updates": self._make_updates(n),
            "filename_mapping": {"old.mp3": "new.mp3"},
        }
        mw_mock.col.media.dir.return_value = str(media_dir)

        class _Note:
            def __init__(self, nid):
                self.id = nid
                self.mod = 1234
                self.fields = ["front", "back"]

        mw_mock.col.get_note.side_effect = lambda nid: _Note(nid)
        mw_mock.col.update_notes.reset_mock()

        count, _opchanges = _apply_media_reference_updates(results)
        batch_sizes = [
            len(call.kwargs["notes"])
            for call in mw_mock.col.update_notes.call_args_list
        ]
        return count, batch_sizes

    def test_one_less_than_batch_size(self, mw_mock, media_dir):
        count, batch_sizes = self._run(mw_mock, BATCH_UPDATE_NOTES_SIZE - 1, media_dir)
        assert count == BATCH_UPDATE_NOTES_SIZE - 1
        assert batch_sizes == [BATCH_UPDATE_NOTES_SIZE - 1]

    def test_exactly_batch_size(self, mw_mock, media_dir):
        count, batch_sizes = self._run(mw_mock, BATCH_UPDATE_NOTES_SIZE, media_dir)
        assert count == BATCH_UPDATE_NOTES_SIZE
        assert batch_sizes == [BATCH_UPDATE_NOTES_SIZE]

    def test_one_more_than_batch_size(self, mw_mock, media_dir):
        count, batch_sizes = self._run(mw_mock, BATCH_UPDATE_NOTES_SIZE + 1, media_dir)
        assert count == BATCH_UPDATE_NOTES_SIZE + 1
        assert batch_sizes == [BATCH_UPDATE_NOTES_SIZE, 1]

    def test_two_batches_exactly(self, mw_mock, media_dir):
        count, batch_sizes = self._run(mw_mock, 2 * BATCH_UPDATE_NOTES_SIZE, media_dir)
        assert count == 2 * BATCH_UPDATE_NOTES_SIZE
        assert batch_sizes == [BATCH_UPDATE_NOTES_SIZE, BATCH_UPDATE_NOTES_SIZE]


class TestAsyncMediaRefThreshold:
    """ASYNC_MEDIA_REF_THRESHOLD decides sync vs async reference updates.

    Just below the threshold the synchronous path must be taken; at and above
    it the async (QueryOp) path must be taken.
    """

    def _run(self, mw_mock, n, force_async=False):
        filename_mapping = {f"old_{i}": f"new_{i}" for i in range(n)}
        media_files = [(f"old_{i}", f"note_{i}") for i in range(n)]
        continuation = MagicMock()
        with (
            patch(
                "export_manager.update_media_references", return_value=(n, None)
            ) as mock_sync,
            patch("export_manager.QueryOp") as mock_qop,
        ):
            schedule_media_reference_updates(
                None,
                filename_mapping,
                media_files,
                None,
                continuation,
                force_async=force_async,
            )
        return mock_sync, mock_qop, continuation

    def test_below_threshold_uses_sync_path(self, mw_mock):
        mock_sync, mock_qop, cont = self._run(mw_mock, ASYNC_MEDIA_REF_THRESHOLD - 1)
        mock_sync.assert_called_once()
        mock_qop.assert_not_called()
        cont.assert_called_once()

    def test_at_threshold_uses_async_path(self, mw_mock):
        mock_sync, mock_qop, cont = self._run(mw_mock, ASYNC_MEDIA_REF_THRESHOLD)
        mock_sync.assert_not_called()
        mock_qop.assert_called_once()
        cont.assert_not_called()  # runs via QueryOp, which is mocked out

    def test_above_threshold_uses_async_path(self, mw_mock):
        mock_sync, mock_qop, cont = self._run(mw_mock, ASYNC_MEDIA_REF_THRESHOLD + 1)
        mock_sync.assert_not_called()
        mock_qop.assert_called_once()
        cont.assert_not_called()

    def test_force_async_overrides_small_set(self, mw_mock):
        mock_sync, mock_qop, cont = self._run(mw_mock, 1, force_async=True)
        mock_sync.assert_not_called()
        mock_qop.assert_called_once()
        cont.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# Media regex patterns
# ──────────────────────────────────────────────────────────────────────


class TestMediaRegexes:
    # ---- sound patterns ----
    def test_sound_regex_simple(self):
        text = "[sound:audio.mp3]"
        for regex in COMPILED_SOUND_REGEXES:
            m = regex.search(text)
            if m:
                assert m.group("fname") == "audio.mp3"
                return
        pytest.fail("No sound regex matched")

    def test_sound_regex_with_path(self):
        text = "[sound:subdir/audio file.mp3]"
        matched = False
        for regex in COMPILED_SOUND_REGEXES:
            m = regex.search(text)
            if m:
                assert "audio file.mp3" in m.group("fname")
                matched = True
        assert matched

    def test_sound_regex_case_insensitive(self):
        text = "[Sound:Test.MP3]"
        matched = any(r.search(text) for r in COMPILED_SOUND_REGEXES)
        assert matched

    # ---- HTML media patterns ----
    def test_img_src_double_quoted(self):
        text = '<img src="photo.jpg">'
        found = False
        for regex in COMPILED_HTML_MEDIA_REGEXES:
            m = regex.search(text)
            if m:
                assert m.group("fname") == "photo.jpg"
                found = True
        assert found

    def test_img_src_single_quoted(self):
        text = "<img src='photo.png'>"
        found = False
        for regex in COMPILED_HTML_MEDIA_REGEXES:
            m = regex.search(text)
            if m:
                assert m.group("fname") == "photo.png"
                found = True
        assert found

    def test_img_src_unquoted(self):
        text = "<img src=photo.gif>"
        found = any(r.search(text) for r in COMPILED_HTML_MEDIA_REGEXES)
        assert found

    def test_audio_src(self):
        text = '<audio src="clip.mp3">'
        found = any(r.search(text) for r in COMPILED_HTML_MEDIA_REGEXES)
        assert found

    def test_object_data(self):
        text = '<object data="file.svg"></object>'
        found = any(r.search(text) for r in COMPILED_HTML_MEDIA_REGEXES)
        assert found

    def test_no_match_on_plain_text(self):
        text = "Just some plain text with no media references"
        found = any(r.search(text) for r in ALL_COMPILED_MEDIA_REGEXES)
        assert not found

    def test_multiple_images_in_field(self):
        text = '<img src="a.jpg"> some text <img src="b.png">'
        fnames = []
        for regex in COMPILED_HTML_MEDIA_REGEXES:
            for m in regex.finditer(text):
                fnames.append(m.group("fname"))
        assert "a.jpg" in fnames
        assert "b.png" in fnames


# ──────────────────────────────────────────────────────────────────────
# _is_valid_media_file
# ──────────────────────────────────────────────────────────────────────


class TestIsValidMediaFile:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "valid.png"
        f.write_bytes(b"\x00" * 200)
        assert _is_valid_media_file(str(f)) is True

    def test_too_small_file(self, tmp_path):
        f = tmp_path / "tiny.png"
        f.write_bytes(b"\x00" * 50)  # < 100 bytes
        assert _is_valid_media_file(str(f)) is False

    def test_missing_file(self):
        assert _is_valid_media_file("/does/not/exist.png") is False

    def test_none_path(self):
        assert _is_valid_media_file(None) is False

    def test_exactly_100_bytes(self, tmp_path):
        f = tmp_path / "exact.png"
        f.write_bytes(b"\x00" * 100)
        assert _is_valid_media_file(str(f)) is True


# ──────────────────────────────────────────────────────────────────────
# _filter_valid_filename_mapping
# ──────────────────────────────────────────────────────────────────────


class TestFilterValidFilenameMapping:
    def test_empty_mapping(self):
        assert _filter_valid_filename_mapping({}) == {}

    def test_filters_invalid_files(self, tmp_path, mw_mock):
        # Create one valid and one invalid file
        valid = tmp_path / "good.png"
        valid.write_bytes(b"\x00" * 200)
        # "bad.png" does not exist

        mapping = {"old_good.png": "good.png", "old_bad.png": "bad.png"}
        result = _filter_valid_filename_mapping(mapping, media_dir=str(tmp_path))
        assert "old_good.png" in result
        assert "old_bad.png" not in result

    def test_all_valid(self, tmp_path, mw_mock):
        for name in ("a.png", "b.jpg"):
            (tmp_path / name).write_bytes(b"\x00" * 200)
        mapping = {"x.png": "a.png", "y.jpg": "b.jpg"}
        result = _filter_valid_filename_mapping(mapping, media_dir=str(tmp_path))
        assert len(result) == 2


# ──────────────────────────────────────────────────────────────────────
# _handle_operation_aborted
# ──────────────────────────────────────────────────────────────────────


class TestHandleOperationAborted:
    @patch("export_manager.aqt.utils.showInfo")
    def test_handles_operation_aborted(self, mock_show, mw_mock):
        err = OperationAbortedError("closed", phase="export")
        result = _handle_operation_aborted(err, "Export")
        assert result is True

    def test_returns_false_for_other_exceptions(self, mw_mock):
        err = ValueError("something else")
        assert _handle_operation_aborted(err, "Export") is False
