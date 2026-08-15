"""Tests for the crowd_anki/anki adapter layer (Phase 0.3 coverage + logic).

These adapters wrap Anki's collection interfaces.  They were previously
imported only by the bootstrap (if at all) with zero test references — this
file exercises their real logic.
"""

import os
from unittest.mock import MagicMock

import pytest

import crowd_anki.anki  # noqa: F401  (package must stay importable)
from crowd_anki.anki.adapters.anki_deck import AnkiDeck
from crowd_anki.anki.adapters.deck_manager import (
    AnkiStaticDeckManager,
    DeckManager as CrowdDeckManager,
)
from crowd_anki.anki.adapters.file_provider import FileProvider
from crowd_anki.anki.adapters.hook_manager import AnkiHookManager
from crowd_anki.anki.adapters.note_model_file_provider import NoteModelFileProvider
from crowd_anki.representation import deck_initializer


def test_file_provider_interface_is_abstract():
    """FileProvider is an ABC — instantiation must fail (it has abstract methods)."""
    with pytest.raises(TypeError):
        FileProvider()


class TestAnkiDeck:
    def test_name_and_dynamic_flags(self):
        deck = AnkiDeck({"name": "Parent::Child", "dyn": 0})
        assert deck.name == "Parent::Child"
        assert deck.is_dynamic is False
        assert deck.data["name"] == "Parent::Child"

    def test_dynamic_deck_detected(self):
        deck = AnkiDeck({"name": "Filtered", "dyn": 1})
        assert deck.is_dynamic is True


class TestAnkiStaticDeckManager:
    def test_all_filters_out_dynamic_decks(self):
        internal = MagicMock()
        internal.all.return_value = [
            {"name": "A", "dyn": 0},
            {"name": "B", "dyn": 1},
        ]
        mgr = AnkiStaticDeckManager(internal_deck_manager=internal)
        names = [d.name for d in mgr.all()]
        assert names == ["A"]

    def test_decks_by_name(self):
        internal = MagicMock()
        internal.all.return_value = [{"name": "A", "dyn": 0}]
        mgr = AnkiStaticDeckManager(internal_deck_manager=internal)
        assert "A" in mgr.decks_by_name()


class TestAnkiHookManager:
    def test_hook_registers(self):
        m = AnkiHookManager()
        m.hooks = MagicMock()
        handler = lambda *a: None  # noqa: E731
        m.hook("exportersList", handler)
        m.hooks.addHook.assert_called_once_with("exportersList", handler)

    def test_unhook_removes(self):
        m = AnkiHookManager()
        m.hooks = MagicMock()
        handler = lambda *a: None  # noqa: E731
        m.unhook("exportersList", handler)
        m.hooks.remHook.assert_called_once_with("exportersList", handler)


class TestNoteModelFileProvider:
    def test_post_init_loads_models_filtering_none(self):
        col = MagicMock()
        col.models.get.side_effect = lambda mid: {1: {"id": 1}, 2: None}[mid]
        provider = NoteModelFileProvider(col, [1, 2])
        assert len(provider.models) == 1
        assert provider.models[0]["id"] == 1

    def test_get_files_returns_underscore_files_in_media_dir(self, tmp_path):
        media = tmp_path / "media"
        media.mkdir()
        (media / "_keep.png").write_bytes(b"x")
        (media / "_keep2.jpg").write_bytes(b"x")
        (media / "ignore.png").write_bytes(b"x")

        col = MagicMock()
        col.media.dir.return_value = str(media)
        col.models.get.return_value = {"id": 1}
        provider = NoteModelFileProvider(col, [1])
        # belongs_to_any_model returns truthy for any file here
        provider.belongs_to_any_model = lambda f: True

        files = provider.get_files()
        assert files == {"_keep.png", "_keep2.jpg"}


class TestDeckInitializer:
    def test_from_collection_returns_none_when_deck_missing(self):
        col = MagicMock()
        col.decks.by_name.return_value = None
        assert deck_initializer.from_collection(col, "Missing Deck") is None

    def test_from_collection_returns_none_for_dynamic_deck(self):
        col = MagicMock()
        col.decks.by_name.return_value = {"name": "Dyn", "dyn": True, "id": 1}
        assert deck_initializer.from_collection(col, "Dyn") is None

    def test_get_card_ids_builds_query_and_delegates(self):
        fake_self = MagicMock()
        fake_self.children.return_value = [("Child", 2)]
        fake_self.col.db.list.return_value = [1, 2, 3]
        result = deck_initializer.get_card_ids(fake_self, 1, children=True)
        assert result == [1, 2, 3]
        # Query must reference the deck ids list
        query = fake_self.col.db.list.call_args[0][0]
        assert "cards" in query and "did" in query
