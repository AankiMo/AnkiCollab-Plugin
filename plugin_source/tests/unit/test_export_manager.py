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
    _handle_operation_aborted,
    ASYNC_MEDIA_REF_THRESHOLD,
    BATCH_UPDATE_NOTES_SIZE,
)
from utils import OperationAbortedError

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────


class TestExportConstants:
    def test_async_media_ref_threshold_positive(self):
        assert ASYNC_MEDIA_REF_THRESHOLD > 0

    def test_batch_update_notes_size_positive(self):
        assert BATCH_UPDATE_NOTES_SIZE > 0


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
