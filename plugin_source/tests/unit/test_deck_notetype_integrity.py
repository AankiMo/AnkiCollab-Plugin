"""Mutation-driven tests for the notetype-schema integrity logic in deck.py.

Targets the survived mutants found in the before-run on
``crowd_anki/representation/deck.py``:

- ``_check_fields_compatible``: default-value handling for missing ``flds``,
  the extra-fields logging branch, and the malformed-input fallback.
- ``_are_notetypes_compatible``: the projektanki fields-only path vs the
  non-projektanki full-detection path, missing ``name`` handling, and the
  error fallback.
- ``_assess_change_risk``: removed-fields, reorder-threshold, and boundary
  cases for position-change counting.
"""

import logging
import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import make_notetype

from crowd_anki.representation import deck as deck_module
from crowd_anki.representation.deck import Deck
from crowd_anki.representation.note_model import NoteModel


def _make_deck():
    return Deck(MagicMock(), {"name": "D", "crowdanki_uuid": "x", "id": 1})


def _patch_logger():
    return patch.object(deck_module.logger, "info")


# ──────────────────────────────────────────────────────────────────────
# _check_fields_compatible
# ──────────────────────────────────────────────────────────────────────


class TestCheckFieldsCompatible:
    def test_missing_remote_flds_is_treated_as_empty(self):
        """Remote without a ``flds`` key is compatible (treated as empty set)."""
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B"])
        del remote["flds"]
        local = make_notetype(name="Basic", fields=["A", "B"])
        assert deck._check_fields_compatible(remote, local) is True

    def test_missing_local_flds_with_empty_remote(self):
        """Local without ``flds`` plus empty remote is compatible (both empty)."""
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=[])
        local = make_notetype(name="Basic", fields=["A", "B"])
        del local["flds"]
        assert deck._check_fields_compatible(remote, local) is True

    def test_remote_subset_of_local(self):
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B"])
        local = make_notetype(name="Basic", fields=["A", "B", "MyCustom"])
        assert deck._check_fields_compatible(remote, local) is True

    def test_remote_field_missing_in_local(self):
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B", "C"])
        local = make_notetype(name="Basic", fields=["A", "B"])
        assert deck._check_fields_compatible(remote, local) is False

    def test_logs_when_local_has_extra_fields(self):
        """The extra-fields info log must fire exactly when compatible + extra."""
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B"])
        local = make_notetype(name="Basic", fields=["A", "B", "Extra"])
        with _patch_logger() as mock_info:
            assert deck._check_fields_compatible(remote, local) is True
        assert mock_info.called
        msg = mock_info.call_args.args[0]
        assert "additional fields" in msg
        assert "Extra" in msg

    def test_no_log_when_compatible_but_equal_lengths(self):
        """Equal-length compatible models must NOT log the extra-fields message."""
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B"])
        local = make_notetype(name="Basic", fields=["A", "B"])
        with _patch_logger() as mock_info:
            assert deck._check_fields_compatible(remote, local) is True
        # The info log is for the extra-fields case only (len(local) > len(remote)).
        assert not mock_info.called

    def test_no_log_when_incompatible_but_local_larger(self):
        """Incompatible (remote not subset) must not log, even if local is larger."""
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B", "D"])
        local = make_notetype(name="Basic", fields=["A", "C", "E", "F"])
        with _patch_logger() as mock_info:
            assert deck._check_fields_compatible(remote, local) is False
        assert not mock_info.called

    def test_malformed_flds_returns_false(self):
        """Non-dict entries in ``flds`` must be treated as incompatible, not crash."""
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B"])
        remote["flds"] = ["A", "B"]  # plain strings, not dicts -> f["name"] raises
        local = make_notetype(name="Basic", fields=["A", "B"])
        assert deck._check_fields_compatible(remote, local) is False


# ──────────────────────────────────────────────────────────────────────
# _are_notetypes_compatible
# ──────────────────────────────────────────────────────────────────────


class TestAreNotetypesCompatible:
    def test_projektanki_mixed_case_local_extra_field(self):
        """ProjektAnki (mixed case) uses the lenient fields-only check.

        Remote fields are a subset of local -> compatible even though the local
        notetype has an extra field that the strict path would flag as a change.
        """
        deck = _make_deck()
        remote = make_notetype(name="ProjektAnki Test", fields=["A", "B"])
        local = make_notetype(name="ProjektAnki Test", fields=["A", "B", "Extra"])
        nm = NoteModel(remote)
        assert deck._are_notetypes_compatible(nm, local) is True

    def test_projektanki_template_difference_still_compatible(self):
        """Fields-only check ignores template differences for projektanki."""
        deck = _make_deck()
        remote = make_notetype(
            name="ProjektAnki Test",
            fields=["A", "B"],
            templates=[{"name": "Card 1", "qfmt": "{{A}}", "afmt": "x", "ord": 0}],
        )
        local = make_notetype(
            name="ProjektAnki Test",
            fields=["A", "B"],
            templates=[{"name": "Card 1", "qfmt": "{{B}}", "afmt": "y", "ord": 0}],
        )
        nm = NoteModel(remote)
        assert deck._are_notetypes_compatible(nm, local) is True

    def test_missing_name_on_both_models(self):
        """Both notetypes missing ``name`` -> no changes detected -> compatible."""
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B"])
        del remote["name"]
        local = make_notetype(name="Basic", fields=["A", "B"])
        del local["name"]
        nm = NoteModel(remote)
        assert deck._are_notetypes_compatible(nm, local) is True

    def test_non_projektanki_template_difference_incompatible(self):
        """Non-projektanki models must match templates too -> incompatible."""
        deck = _make_deck()
        remote = make_notetype(
            name="Basic",
            fields=["A", "B"],
            templates=[{"name": "Card 1", "qfmt": "{{A}}", "afmt": "x", "ord": 0}],
        )
        local = make_notetype(
            name="Basic",
            fields=["A", "B"],
            templates=[{"name": "Card 1", "qfmt": "{{B}}", "afmt": "y", "ord": 0}],
        )
        nm = NoteModel(remote)
        assert deck._are_notetypes_compatible(nm, local) is False

    def test_non_projektanki_identical_is_compatible(self):
        deck = _make_deck()
        remote = make_notetype(name="Basic", fields=["A", "B"])
        local = make_notetype(name="Basic", fields=["A", "B"])
        nm = NoteModel(remote)
        assert deck._are_notetypes_compatible(nm, local) is True

    def test_malformed_remote_dict_returns_false(self):
        """If remote_model.anki_dict is unusable, err on the side of incompatible."""
        deck = _make_deck()
        nm = NoteModel(None)  # anki_dict is {}
        local = make_notetype(name="Basic", fields=["A", "B"])
        nm.anki_dict = None  # force the exception path
        assert deck._are_notetypes_compatible(nm, local) is False


# ──────────────────────────────────────────────────────────────────────
# _assess_change_risk
# ──────────────────────────────────────────────────────────────────────


class TestAssessChangeRisk:
    def test_old_missing_flds_is_no_risk(self):
        """Old model without ``flds`` -> no removed fields -> no risk."""
        deck = _make_deck()
        old = make_notetype(name="Basic", fields=["A", "B"])
        del old["flds"]
        new = make_notetype(name="Basic", fields=["A", "B"])
        assert deck._assess_change_risk(old, new) is False

    def test_new_missing_flds_with_empty_old(self):
        """Both effectively empty field sets -> no risk."""
        deck = _make_deck()
        old = make_notetype(name="Basic", fields=[])
        new = make_notetype(name="Basic", fields=["A", "B"])
        del new["flds"]
        assert deck._assess_change_risk(old, new) is False

    def test_single_adjacent_swap_of_four_is_no_risk(self):
        """One adjacent swap among 4 fields is NOT > half changed -> no risk."""
        deck = _make_deck()
        old = make_notetype(name="Basic", fields=["A", "B", "C", "D"])
        new = make_notetype(name="Basic", fields=["B", "A", "C", "D"])
        assert deck._assess_change_risk(old, new) is False

    def test_full_reversal_of_two_is_risk(self):
        deck = _make_deck()
        old = make_notetype(name="Basic", fields=["A", "B"])
        new = make_notetype(name="Basic", fields=["B", "A"])
        assert deck._assess_change_risk(old, new) is True

    def test_removed_field_is_risk(self):
        deck = _make_deck()
        old = make_notetype(name="Basic", fields=["A", "B", "C"])
        new = make_notetype(name="Basic", fields=["A", "B"])
        assert deck._assess_change_risk(old, new) is True

    def test_malformed_old_model_returns_true(self):
        """If risk cannot be assessed, err on the side of caution (True)."""
        deck = _make_deck()
        new = make_notetype(name="Basic", fields=["A", "B"])
        assert deck._assess_change_risk(None, new) is True
