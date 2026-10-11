"""Meta-tests: prove the fake Anki collection is strict (Phase 0.2).

A typo'd or renamed Anki API call (e.g. ``col.decks.get_deck(...)`` instead of
``col.decks.get(...)``) must raise ``AttributeError``.  A permissive
``MagicMock`` would silently accept any method name and let that regression
pass — exactly the failure mode this file exists to prevent.

These tests are designed to FAIL against the old, permissive ``FakeCol`` and
PASS once the core interfaces (``decks``, ``models``, ``db``, ``tags``,
``media``) are created with ``spec_set=``.
"""

import pytest

from tests.mocks import FakeCol, create_mock_mw


@pytest.fixture
def strict_col():
    return FakeCol()


def test_decks_rejects_unknown_method(strict_col):
    with pytest.raises(AttributeError):
        strict_col.decks.get_deck_that_does_not_exist()


def test_models_rejects_unknown_method(strict_col):
    with pytest.raises(AttributeError):
        strict_col.models.get_model_that_does_not_exist()


def test_db_rejects_unknown_method(strict_col):
    with pytest.raises(AttributeError):
        strict_col.db.query_table_that_does_not_exist()


def test_tags_rejects_unknown_method(strict_col):
    with pytest.raises(AttributeError):
        strict_col.tags.purge_all_tags_that_do_not_exist()


def test_media_rejects_unknown_method(strict_col):
    with pytest.raises(AttributeError):
        strict_col.media.upload_that_does_not_exist()


def test_typo_style_call_is_caught(strict_col):
    """The exact class of bug from the audit: col.decks.get_deck(...)."""
    with pytest.raises(AttributeError):
        strict_col.decks.get_deck(1)


def test_real_methods_remain_configureable(strict_col):
    """Strictness must not break configuring real method names."""
    strict_col.decks.get.return_value = {"id": 1, "name": "Default"}
    assert strict_col.decks.get(1)["name"] == "Default"

    strict_col.db.scalar.return_value = 42
    assert strict_col.db.scalar("select 1") == 42


def test_create_mock_mw_uses_strict_collection():
    """The fixture every unit test uses must also be strict."""
    mw = create_mock_mw()
    with pytest.raises(AttributeError):
        mw.col.decks.get_deck_that_does_not_exist()
