"""Mutation-driven tests for note.py card/deck synchronization logic.

Covers survivors / uncovered branches in:
- ``_bulk_update_notes_preserving_placement``: filtered-card odid update
  (normal vs filtered vs already-correct), ignore_deck_movement, empty input.
- ``_sync_sibling_suspension_status``: missing anki_object, missing previous
  cards, empty sibling data, exception fallback.
- ``bulk_add_notes``: suspend_new_cards path.

test_import_safety.py already covers the basic filtered-deck/ignore/move cases;
these close the remaining branches.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import (
    create_mock_collection,
    make_note_dict,
    make_notetype,
    MockAnkiNote,
)

from crowd_anki.representation.note import Note
from crowd_anki.representation.note_model import NoteModel


def _update_note(card_ids, uuid="uuid1"):
    """Build an update note with the given card ids, like test_import_safety."""
    note = Note.from_json(make_note_dict(fields=["new", "new"], guid=uuid))
    mock = MockAnkiNote()
    mock.fields = ["old", "old"]
    mock.tags = []
    mock.id = 1
    mock._card_ids = list(card_ids)
    note.anki_object = mock
    note.anki_object.__dict__.update(note.anki_object_dict)
    return note


def _config(ignore_deck_movement=False):
    cfg = MagicMock()
    cfg.ignore_deck_movement = ignore_deck_movement
    return cfg


# ──────────────────────────────────────────────────────────────────────
# _bulk_update_notes_preserving_placement
# ──────────────────────────────────────────────────────────────────────


class TestBulkUpdatePreservingPlacement:
    def test_empty_update_notes_returns(self):
        col = create_mock_collection()
        Note._bulk_update_notes_preserving_placement(col, [], {}, _config())
        col.update_notes.assert_not_called()

    def test_normal_card_moved_to_target_deck(self):
        col = create_mock_collection()
        note = _update_note([100])
        col.db.all.return_value = [(100, 5, 0)]  # id, did, odid
        col.decks.id = MagicMock(return_value=10)
        Note._bulk_update_notes_preserving_placement(
            col, [note], {"uuid1": "Target"}, _config()
        )
        col.set_deck.assert_called_once()
        moved = col.set_deck.call_args.args[0]
        assert 100 in moved

    def test_filtered_card_odid_updated_via_update_cards(self):
        """Filtered card (odid != 0, != target) gets its odid updated, not moved."""
        col = create_mock_collection()
        note = _update_note([100])
        col.db.all.return_value = [(100, 5, 3)]  # odid=3, target=10
        col.decks.id = MagicMock(return_value=10)
        card = MagicMock()
        card.odid = 3
        col.get_card.return_value = card
        Note._bulk_update_notes_preserving_placement(
            col, [note], {"uuid1": "Target"}, _config()
        )
        # Normal move is NOT used for filtered cards.
        col.set_deck.assert_not_called()
        col.update_cards.assert_called_once()
        assert card.odid == 10

    def test_filtered_card_odid_already_target_not_updated(self):
        col = create_mock_collection()
        note = _update_note([100])
        col.db.all.return_value = [(100, 5, 10)]  # odid == target 10
        col.decks.id = MagicMock(return_value=10)
        Note._bulk_update_notes_preserving_placement(
            col, [note], {"uuid1": "Target"}, _config()
        )
        col.set_deck.assert_not_called()
        col.update_cards.assert_not_called()

    def test_ignore_deck_movement_no_query(self):
        col = create_mock_collection()
        note = _update_note([100])
        Note._bulk_update_notes_preserving_placement(
            col, [note], {"uuid1": "Target"}, _config(ignore_deck_movement=True)
        )
        col.db.all.assert_not_called()
        col.set_deck.assert_not_called()

    def test_note_without_anki_object_skipped(self):
        col = create_mock_collection()
        note = Note.from_json(make_note_dict(guid="uuid1"))
        note.anki_object = None
        Note._bulk_update_notes_preserving_placement(
            col, [note], {"uuid1": "Target"}, _config(ignore_deck_movement=True)
        )
        col.update_notes.assert_called_once()  # content update still happens


# ──────────────────────────────────────────────────────────────────────
# _sync_sibling_suspension_status
# ──────────────────────────────────────────────────────────────────────


class TestSyncSiblingSuspension:
    def test_note_without_anki_object_skipped(self):
        col = create_mock_collection()
        note = MagicMock()
        note.anki_object = None
        Note._sync_sibling_suspension_status(col, [note], {1: {100}})
        col.sched.suspend_cards.assert_not_called()

    def test_no_previous_cards_skipped(self):
        col = create_mock_collection()
        note = MagicMock()
        note.anki_object = MagicMock()
        note.anki_object.id = 1
        note.anki_object.card_ids.return_value = [100, 101]
        Note._sync_sibling_suspension_status(col, [note], {})
        col.db.all.assert_not_called()
        col.sched.suspend_cards.assert_not_called()

    def test_empty_sibling_data_skipped(self):
        col = create_mock_collection()
        note = MagicMock()
        note.anki_object = MagicMock()
        note.anki_object.id = 1
        note.anki_object.card_ids.return_value = [100, 101]
        col.db.all.return_value = []
        Note._sync_sibling_suspension_status(col, [note], {1: {100}})
        col.sched.suspend_cards.assert_not_called()

    def test_all_siblings_suspended_suspends_new(self):
        col = create_mock_collection()
        note = MagicMock()
        note.anki_object = MagicMock()
        note.anki_object.id = 1
        note.anki_object.card_ids.return_value = [100, 101]
        col.db.all.return_value = [(100, -1)]  # queue -1 = suspended
        Note._sync_sibling_suspension_status(col, [note], {1: {100}})
        suspended = col.sched.suspend_cards.call_args.args[0]
        assert 101 in suspended

    def test_query_exception_skips(self):
        col = create_mock_collection()
        note = MagicMock()
        note.anki_object = MagicMock()
        note.anki_object.id = 1
        note.anki_object.card_ids.return_value = [100, 101]
        col.db.all.side_effect = RuntimeError("boom")
        Note._sync_sibling_suspension_status(col, [note], {1: {100}})
        col.sched.suspend_cards.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# bulk_add_notes
# ──────────────────────────────────────────────────────────────────────


class TestBulkAddNotes:
    def test_suspend_new_cards_when_configured(self):
        col = create_mock_collection()
        note = _update_note([100, 101])
        cfg = MagicMock()
        cfg.suspend_new_cards = True
        with patch("crowd_anki.representation.note.AddNoteRequest") as m_req:
            Note.bulk_add_notes(col, [note], 1, cfg)
        col.add_notes.assert_called_once()
        suspended = col.sched.suspend_cards.call_args.args[0]
        assert 100 in suspended
        assert 101 in suspended

    def test_no_suspend_when_not_configured(self):
        col = create_mock_collection()
        note = _update_note([100])
        cfg = MagicMock()
        cfg.suspend_new_cards = False
        with patch("crowd_anki.representation.note.AddNoteRequest"):
            Note.bulk_add_notes(col, [note], 1, cfg)
        col.add_notes.assert_called_once()
        col.sched.suspend_cards.assert_not_called()
