"""Tests for the media glue files: media_exporter, media_export, media_import.

These modules sit between the export pipeline and the media manager.  The
pure extraction functions (CSS/template media references) and the small
config/file helpers are exercised directly; ``copy_content`` runs against a
real temp filesystem.
"""

from unittest.mock import patch

import pytest

from media_exporter import (
    gather_media_from_css,
    gather_media_from_template,
    gather_media_from_template_side,
    get_notetype_media,
)
from media_export import get_configured_exts, get_configured_search_field
from media_import import copy_content, file_name_filter


class TestGatherMediaFromCss:
    def test_import_quoted_underscore_css(self):
        css = '@import "_myfile.css";'
        assert gather_media_from_css(css) == ["_myfile.css"]

    def test_url_quoted_and_unquoted(self):
        css = (
            'body { background: url("_img.png"); } .a { background: url(_other.png); }'
        )
        assert gather_media_from_css(css) == ["_img.png", "_other.png"]

    def test_ignores_non_underscore_files(self):
        css = 'url("normal.png") url("_kept.png")'
        assert gather_media_from_css(css) == ["_kept.png"]

    def test_no_media(self):
        assert gather_media_from_css("body { color: red; }") == []


class TestGatherMediaFromTemplateSide:
    def test_sound_tag(self):
        assert gather_media_from_template_side("[sound:_audio.mp3]") == ["_audio.mp3"]

    def test_quoted_and_src(self):
        tmpl = '<img src="_pic.png"><source src="_clip.mp4">'
        result = gather_media_from_template_side(tmpl)
        assert "_pic.png" in result and "_clip.mp4" in result

    def test_ignores_non_underscore(self):
        assert gather_media_from_template_side('<img src="pic.png">') == []

    def test_no_media(self):
        assert gather_media_from_template_side("{{Front}}") == []


class TestGatherMediaFromTemplate:
    def test_combines_question_and_answer(self):
        tmpl = {"qfmt": "[sound:_q.mp3]", "afmt": '<img src="_a.png">'}
        result = gather_media_from_template(tmpl)
        assert result == ["_q.mp3", "_a.png"]


class TestGetNotetypeMedia:
    def test_css_plus_templates(self):
        notetype = {
            "css": 'url("_bg.css.png")',
            "tmpls": [
                {"qfmt": "[sound:_one.mp3]", "afmt": ""},
                {"qfmt": "", "afmt": "[sound:_two.mp3]"},
            ],
        }
        result = get_notetype_media(notetype)
        assert "_bg.css.png" in result
        assert "_one.mp3" in result
        assert "_two.mp3" in result


class TestGetConfiguredExts:
    def test_audio_only_returns_audio_exts(self):
        with patch("media_export.AUDIO_EXTS", {"mp3", "ogg"}):
            assert get_configured_exts({"audio_only": True}) == {"mp3", "ogg"}

    def test_no_audio_only_returns_none(self):
        assert get_configured_exts({"audio_only": False}) is None
        assert get_configured_exts({}) is None


class TestGetConfiguredSearchField:
    def test_returns_configured_field(self):
        assert get_configured_search_field({"search_in_field": "Front"}) == "Front"

    def test_returns_none_when_unset(self):
        assert get_configured_search_field({}) is None


class TestCopyContent:
    def test_copies_files_to_media_dir(self, mw_mock, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.mp3").write_bytes(b"audio")
        sub = src / "nested"
        sub.mkdir()
        (sub / "b.png").write_bytes(b"img")

        media_dir = tmp_path / "media"
        media_dir.mkdir()
        mw_mock.col.media.dir.return_value = str(media_dir)

        with patch("media_import.mw", mw_mock):
            count = copy_content(str(src))

        assert count == 2
        assert (media_dir / "a.mp3").read_bytes() == b"audio"
        assert (media_dir / "b.png").read_bytes() == b"img"

    def test_returns_zero_for_missing_path(self, mw_mock, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        mw_mock.col.media.dir.return_value = str(media_dir)
        with patch("media_import.mw", mw_mock):
            assert copy_content(str(tmp_path / "nope")) == 0


class TestFileNameFilter:
    def test_builds_filter_from_pics_and_audio(self):
        # file_name_filter lives in media_import and reads aqt.editor there
        with patch("media_import.aqt") as mock_aqt:
            mock_aqt.editor.pics = ["jpg", "png"]
            mock_aqt.editor.audio = ["mp3", "ogg"]
            result = file_name_filter()
        assert result.startswith("Image & Audio Files (")
        assert "*.jpg" in result and "*.mp3" in result
