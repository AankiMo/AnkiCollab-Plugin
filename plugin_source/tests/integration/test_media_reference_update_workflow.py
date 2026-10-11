"""Media-reference update workflow tests (Phase 3.4).

Targets ``export_manager.update_media_references`` end-to-end: seed a fake
Anki media directory, run the real collect → filter → upload → note-reference-
update pipeline (the upload step's HTTP is not involved here; everything else
is real), and assert the *actual note field contents* afterward — not just that
the update function was called.
"""

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration

from export_manager import update_media_references


def _note(fields, note_id=1):
    note = MagicMock()
    note.id = note_id
    note.fields = list(fields)
    return note


class TestMediaReferenceUpdateWorkflow:
    def _seed_media(self, mw_mock, tmp_path, files):
        media = tmp_path / "media"
        media.mkdir()
        for name, data in files.items():
            (media / name).write_bytes(data)
        mw_mock.col.media.dir.return_value = str(media)
        return media

    def test_one_note_one_file(self, mw_mock, tmp_path):
        self._seed_media(mw_mock, tmp_path, {"new_audio.mp3": b"x" * 100})
        mw_mock.col.db.first.return_value = (1,)
        note = _note(["[sound:old_audio.mp3]", "back content"])
        mw_mock.col.get_note.return_value = note

        count, _ = update_media_references(
            {"old_audio.mp3": "new_audio.mp3"}, [("old_audio.mp3", "guid-1")]
        )

        assert count == 1
        assert note.fields[0] == "[sound:new_audio.mp3]"
        assert note.fields[1] == "back content"  # untouched
        mw_mock.col.update_notes.assert_called_once()

    def test_one_note_multiple_files(self, mw_mock, tmp_path):
        self._seed_media(
            mw_mock,
            tmp_path,
            {"new_a.mp3": b"x" * 100, "new_b.mp3": b"x" * 100},
        )
        mw_mock.col.db.first.return_value = (1,)
        note = _note(["[sound:old_a.mp3] [sound:old_b.mp3]", ""])
        mw_mock.col.get_note.return_value = note

        count, _ = update_media_references(
            {"old_a.mp3": "new_a.mp3", "old_b.mp3": "new_b.mp3"},
            [("old_a.mp3", "guid-1"), ("old_b.mp3", "guid-1")],
        )

        assert count == 1
        assert note.fields[0] == "[sound:new_a.mp3] [sound:new_b.mp3]"

    def test_multiple_notes_sharing_one_file(self, mw_mock, tmp_path):
        self._seed_media(mw_mock, tmp_path, {"new.png": b"x" * 100})
        mw_mock.col.db.first.side_effect = [(1,), (2,)]  # note ids by guid
        note1 = _note(['<img src="old.png">', ""], note_id=1)
        note2 = _note(['<img src="old.png">', ""], note_id=2)
        mw_mock.col.get_note.side_effect = lambda nid: {1: note1, 2: note2}[nid]

        count, _ = update_media_references(
            {"old.png": "new.png"},
            [("old.png", "guid-1"), ("old.png", "guid-2")],
        )

        assert count == 2
        assert note1.fields[0] == '<img src="new.png">'
        assert note2.fields[0] == '<img src="new.png">'

    def test_multiple_references_in_single_field(self, mw_mock, tmp_path):
        self._seed_media(mw_mock, tmp_path, {"new.mp3": b"x" * 100})
        mw_mock.col.db.first.return_value = (1,)
        note = _note(["[sound:old.mp3] and [sound:old.mp3] again", ""])
        mw_mock.col.get_note.return_value = note

        count, _ = update_media_references(
            {"old.mp3": "new.mp3"}, [("old.mp3", "guid-1")]
        )

        assert count == 1
        # Every occurrence in the field is rewritten
        assert note.fields[0] == "[sound:new.mp3] and [sound:new.mp3] again"

    def test_zero_changes_needed(self, mw_mock, tmp_path):
        self._seed_media(mw_mock, tmp_path, {"new.png": b"x" * 100})
        mw_mock.col.db.first.return_value = (1,)
        # Note already references the NEW filename — no old reference to fix
        note = _note(['<img src="new.png">', ""])
        mw_mock.col.get_note.return_value = note

        count, _ = update_media_references(
            {"old.png": "new.png"}, [("old.png", "guid-1")]
        )

        assert count == 0
        assert note.fields[0] == '<img src="new.png">'  # unchanged
        mw_mock.col.update_notes.assert_not_called()

    def test_missing_new_file_is_filtered_out(self, mw_mock, tmp_path):
        """A mapping whose target file does not exist on disk must be skipped."""
        self._seed_media(mw_mock, tmp_path, {"unrelated.png": b"x" * 100})
        mw_mock.col.db.first.return_value = (1,)
        note = _note(["[sound:old.mp3]", ""])
        mw_mock.col.get_note.return_value = note

        count, _ = update_media_references(
            {"old.mp3": "does_not_exist.mp3"}, [("old.mp3", "guid-1")]
        )

        assert count == 0
        assert note.fields[0] == "[sound:old.mp3]"  # left untouched
        mw_mock.col.update_notes.assert_not_called()
