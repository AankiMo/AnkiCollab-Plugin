"""Mutation-driven tests for deck-structure logic in deck.py.

Covers the survived mutants in the before-run for:
- ``_get_full_deck_name`` (smart subdeck mapping branches)
- ``_save_deck`` (home-deck / conflict / create / subdeck branches)
- ``_create_deck_structure`` (recursion + error fallback)
- ``_rename_deck`` (unique-name suffixing)
- ``_cleanup_temp_deck`` (empty / non-empty / already-deleted / error paths)

The prior tests only asserted ``col.decks.id.called``; these assert the actual
returned names, the saved deck dicts, and the specific deck-API calls.
"""

import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import create_mock_collection

from crowd_anki.representation import deck as deck_module
from crowd_anki.representation.deck import Deck
from crowd_anki.representation.note import Note
from crowd_anki.utils.constants import UUID_FIELD_NAME


def _patch_logger(method="info"):
    return patch.object(deck_module.logger, method)


def _make_deck(name="ServerRoot", deck_uuid="deck-uuid-1", is_child=False, deck_id=1):
    return Deck(
        MagicMock(),
        {"name": name, "crowdanki_uuid": deck_uuid, "id": deck_id},
        is_child=is_child,
    )


# ──────────────────────────────────────────────────────────────────────
# _get_full_deck_name
# ──────────────────────────────────────────────────────────────────────


class TestGetFullDeckName:
    def test_root_no_home_deck(self):
        deck = _make_deck("TopLevel")
        assert deck._get_full_deck_name("", None) == "TopLevel"

    def test_root_with_home_deck(self):
        deck = _make_deck("ServerDeck")
        assert deck._get_full_deck_name("", "MyStudy") == "MyStudy"

    def test_child_standard(self):
        deck = _make_deck("SubDeck")
        assert deck._get_full_deck_name("Parent", None) == "Parent::SubDeck"

    def test_child_nested_under_home_deck(self):
        deck = _make_deck("SubA")
        result = deck._get_full_deck_name("MyStudy", "MyStudy", "ServerRoot")
        assert result == "MyStudy::SubA"

    def test_child_unexpected_mapping_falls_back(self):
        """parent_name not under home_deck -> standard fallback with a warning."""
        deck = _make_deck("SubA")
        with _patch_logger("warning") as mock_warn:
            result = deck._get_full_deck_name("Other::Parent", "MyStudy", "ServerRoot")
        assert result == "Other::Parent::SubA"
        assert mock_warn.called

    def test_missing_name_defaults(self):
        deck = Deck(MagicMock(), {"crowdanki_uuid": "x", "id": 1})
        assert deck._get_full_deck_name("", None) == "Unknown Deck"


# ──────────────────────────────────────────────────────────────────────
# _save_deck
# ──────────────────────────────────────────────────────────────────────


class TestSaveDeck:
    def test_root_with_home_deck_existing(self):
        col = create_mock_collection()
        col.decks._store[10] = {
            "id": 10,
            "name": "MyStudy",
            "crowdanki_uuid": "home-uuid",
        }
        deck = _make_deck()
        result = deck._save_deck(col, "", "MyStudy")
        assert result == "MyStudy"
        # Existing home deck is reused (root_deck_id resolved to the existing deck).
        assert deck.anki_dict["name"] == "MyStudy"
        assert deck.root_deck_id == 10

    def test_root_with_home_deck_missing_creates(self):
        col = create_mock_collection()
        deck = _make_deck()
        result = deck._save_deck(col, "", "MyStudy")
        assert result == "MyStudy"
        assert col.decks.id("MyStudy", create=False) is not None
        assert deck.anki_dict["name"] == "MyStudy"

    def test_root_no_home_deck_uses_server_name(self):
        col = create_mock_collection()
        deck = _make_deck("ServerRoot")
        result = deck._save_deck(col, "", None)
        assert result == "ServerRoot"
        assert deck.anki_dict["name"] == "ServerRoot"
        assert col.decks.id("ServerRoot", create=False) is not None

    def test_root_no_home_deck_existing_by_uuid(self):
        col = create_mock_collection()
        col.decks._store[5] = {
            "id": 5,
            "name": "ServerRoot",
            "crowdanki_uuid": "deck-uuid-1",
        }
        deck = _make_deck("ServerRoot")
        result = deck._save_deck(col, "", None)
        assert result == "ServerRoot"
        # Existing deck (id 5) was found by UUID — no rename, root_deck_id = 5.
        assert deck.root_deck_id == 5
        assert "AnkiCollab" not in result

    def test_root_name_conflict_renames(self):
        col = create_mock_collection()
        col.decks._store[9] = {
            "id": 9,
            "name": "ServerRoot",
            "crowdanki_uuid": "other-uuid",
        }
        deck = _make_deck("ServerRoot")
        result = deck._save_deck(col, "", None)
        assert result != "ServerRoot"
        assert "AnkiCollab" in result
        assert deck.anki_dict["name"] == result

    def test_subdeck_conflict_not_renamed(self):
        col = create_mock_collection()
        col.decks._store[9] = {
            "id": 9,
            "name": "Parent::Child",
            "crowdanki_uuid": "other-uuid",
        }
        deck = _make_deck("Child")
        result = deck._save_deck(col, "Parent", None, "ServerRoot")
        assert result == "Parent::Child"
        assert "AnkiCollab" not in result

    def test_subdeck_no_conflict_created(self):
        col = create_mock_collection()
        deck = _make_deck("Child")
        result = deck._save_deck(col, "Parent", None, "ServerRoot")
        assert result == "Parent::Child"
        assert col.decks.id("Parent::Child", create=False) is not None


# ──────────────────────────────────────────────────────────────────────
# _create_deck_structure
# ──────────────────────────────────────────────────────────────────────


class TestCreateDeckStructure:
    def test_creates_root_and_children(self):
        col = create_mock_collection()
        child = _make_deck("Sub", deck_uuid="child-uuid-1", deck_id=2)
        child.is_child = True
        deck = _make_deck("Root")
        deck.children = [child]
        root_name = deck._create_deck_structure(col, "", None, "Root")
        assert root_name == "Root"
        assert col.decks.id("Root", create=False) is not None
        assert col.decks.id("Root::Sub", create=False) is not None
        assert deck.root_deck_id is not None

    def test_creates_under_home_deck(self):
        col = create_mock_collection()
        child = _make_deck("Sub", deck_uuid="child-uuid-1", deck_id=2)
        child.is_child = True
        deck = _make_deck("Root")
        deck.children = [child]
        root_name = deck._create_deck_structure(col, "", "MyStudy", "Root")
        assert root_name == "MyStudy"
        assert col.decks.id("MyStudy", create=False) is not None
        assert col.decks.id("MyStudy::Sub", create=False) is not None


# ──────────────────────────────────────────────────────────────────────
# _rename_deck
# ──────────────────────────────────────────────────────────────────────


class TestRenameDeck:
    def test_renames_to_ankicollab(self):
        col = create_mock_collection()
        col.decks._store[1] = {
            "id": 1,
            "name": "Existing",
            "crowdanki_uuid": "old",
        }
        assert Deck._rename_deck("Existing", col) == "Existing (AnkiCollab)"

    def test_increments_on_further_conflict(self):
        col = create_mock_collection()
        col.decks._store[1] = {
            "id": 1,
            "name": "Existing",
            "crowdanki_uuid": "old",
        }
        col.decks._store[2] = {
            "id": 2,
            "name": "Existing (AnkiCollab)",
            "crowdanki_uuid": "old2",
        }
        assert Deck._rename_deck("Existing", col) == "Existing (AnkiCollab)_2"


# ──────────────────────────────────────────────────────────────────────
# _cleanup_temp_deck
# ──────────────────────────────────────────────────────────────────────


class TestCleanupTempDeck:
    def _deck(self):
        deck = _make_deck()
        deck.collection = create_mock_collection()
        return deck

    def test_no_temp_deck_id_returns(self):
        deck = self._deck()
        with _patch_logger("debug") as mock_debug:
            deck._cleanup_temp_deck(deck.collection, None, "name", "ctx")
        assert mock_debug.called

    def test_already_deleted(self):
        deck = self._deck()
        deck.collection.decks.get = MagicMock(return_value=None)
        with _patch_logger("info") as mock_info:
            deck._cleanup_temp_deck(deck.collection, 42, "_tmp", "ctx")
        assert mock_info.called

    def test_empty_deck_removed(self):
        deck = self._deck()
        deck.collection.decks._store[42] = {
            "id": 42,
            "name": "_ankicollab_import_abc",
            "crowdanki_uuid": "",
        }
        deck.collection.decks.card_count = MagicMock(return_value=0)
        deck._cleanup_temp_deck(deck.collection, 42, "_tmp", "success")
        assert 42 not in deck.collection.decks._store
        deck.collection.decks.remove.assert_called_with([42])

    def test_deck_with_cards_not_removed(self):
        deck = self._deck()
        deck.collection.decks._store[42] = {
            "id": 42,
            "name": "_ankicollab_import_abc",
            "crowdanki_uuid": "",
        }
        deck.collection.decks.card_count = MagicMock(return_value=3)
        deck._cleanup_temp_deck(deck.collection, 42, "_tmp", "ctx")
        assert 42 in deck.collection.decks._store
        deck.collection.decks.remove.assert_not_called()

    def test_get_exception_treated_as_missing(self):
        deck = self._deck()
        deck.collection.decks.get = MagicMock(side_effect=Exception("boom"))
        with _patch_logger("info") as mock_info:
            deck._cleanup_temp_deck(deck.collection, 42, "_tmp", "ctx")
        assert mock_info.called
        deck.collection.decks.remove.assert_not_called()
