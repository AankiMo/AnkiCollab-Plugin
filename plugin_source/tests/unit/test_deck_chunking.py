"""CHUNK_SIZE boundary tests for crowd_anki/representation/deck.py.

``CHUNK_SIZE = 1000`` governs note-UUID lookup batching during bulk import.
A regression that breaks batching at the boundaries (e.g. off-by-one, or a
``<`` vs ``<=`` flip) silently degrades import performance or correctness on
large decks.  These tests pin the exact number of chunks and their sizes at
CHUNK_SIZE - 1, CHUNK_SIZE, CHUNK_SIZE + 1, and 2 * CHUNK_SIZE note counts.
"""

from unittest.mock import MagicMock, patch

import pytest

from crowd_anki.representation.deck import CHUNK_SIZE, Deck
from crowd_anki.representation.note import Note


class _FakeImportNote:
    """Minimal stand-in for crowd_anki Note as used by the bulk importer."""

    def __init__(self, uuid, model_uuid="model1"):
        self._uuid = uuid
        self.note_model_uuid = model_uuid

    def get_uuid(self):
        return self._uuid


def _make_deck(n):
    deck = Deck(lambda *a, **kw: None, {"name": "Test", "id": 1})
    deck.notes = [_FakeImportNote(f"uuid_{i}") for i in range(n)]
    return deck


@pytest.fixture
def mock_import_config():
    cfg = MagicMock()
    cfg.new_notes_home_deck = None
    cfg.home_deck = None
    return cfg


class TestChunkSizeBatching:
    @pytest.mark.parametrize(
        "n,expected_calls,expected_chunks",
        [
            (CHUNK_SIZE - 1, 1, [CHUNK_SIZE - 1]),
            (CHUNK_SIZE, 1, [CHUNK_SIZE]),
            (CHUNK_SIZE + 1, 2, [CHUNK_SIZE, 1]),
            (2 * CHUNK_SIZE, 2, [CHUNK_SIZE, CHUNK_SIZE]),
            (2 * CHUNK_SIZE + 1, 3, [CHUNK_SIZE, CHUNK_SIZE, 1]),
        ],
    )
    def test_note_uuid_lookup_batches_at_boundaries(
        self,
        mw_mock,
        mock_import_config,
        n,
        expected_calls,
        expected_chunks,
    ):
        deck = _make_deck(n)
        deck.metadata = MagicMock()
        deck.metadata.models = {"model1": MagicMock()}

        col = MagicMock()
        col.db.all.return_value = []  # no pre-existing notes
        progress = MagicMock()

        with (
            patch("crowd_anki.representation.deck.mw", mw_mock),
            patch.object(Note, "bulk_add_notes"),
            patch.object(Note, "_bulk_update_notes_preserving_placement"),
            patch.object(Deck, "_batch_process_new_notes"),
            patch.object(Deck, "_batch_process_update_notes"),
            patch.object(Deck, "_restore_original_note_ids"),
        ):
            deck._bulk_process_all_notes(
                col, deck.notes, mock_import_config, progress, {}
            )

        calls = col.db.all.call_args_list
        assert (
            len(calls) == expected_calls
        ), f"expected {expected_calls} batched lookup(s) for {n} notes, got {len(calls)}"
        # args[0] is the query string; the remaining positional args are the chunk.
        chunk_sizes = [len(call.args) - 1 for call in calls]
        assert chunk_sizes == expected_chunks

        # The SQL placeholders must match the number of uuids passed.
        for call in calls:
            query = call.args[0]
            chunk = call.args[1:]
            assert query.count("?") == len(chunk)

    def test_batch_size_constant_is_sane(self):
        assert CHUNK_SIZE > 0
        assert CHUNK_SIZE >= 100  # large enough that batching is meaningful
