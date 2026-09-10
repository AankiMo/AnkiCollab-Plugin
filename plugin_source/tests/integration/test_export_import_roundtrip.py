"""Export → import round-trip tests (Phase 3.3).

The highest-value workflow test: build a rich collection A, export it through
the real ``deck_initializer.from_collection`` + ``Deck`` JSON serialization,
then import that exported representation back through the real
``deck_initializer.from_json`` deserialization into a fresh collection B, and
require semantic equality between A and B (normalizing only what is *expected*
to differ: local numeric IDs and local mod timestamps).

This exercises export and import together against a shared ground truth, so a
regression in either direction (a dropped field, a reordered template, a
corrupted UUID) shows up here even if each side's isolated tests are green.
"""

import json

import pytest

pytestmark = pytest.mark.integration

from crowd_anki.representation import deck_initializer
from crowd_anki.representation.deck import Deck
from tests.conftest import make_notetype


class TestExportImportRoundtrip:
    def _seed(self, col):
        basic = make_notetype(
            name="Basic",
            fields=["Front", "Back"],
            model_id=100,
            model_uuid="model-basic",
            css=".card { color: blue; }",
        )
        col.add_model(basic)
        cloze = make_notetype(
            name="Cloze",
            fields=["Text", "Extra"],
            model_id=101,
            model_uuid="model-cloze",
        )
        col.add_model(cloze)

        parent_did = col.add_deck("Parent", deck_uuid="deck-parent")
        child_did = col.add_deck("Parent::Child", deck_uuid="deck-child")

        col.add_note_record(
            guid="note-a",
            mid=100,
            fields=["Front A", "Back A"],
            tags=["tag1", "tag2"],
            did=parent_did,
        )
        col.add_note_record(
            guid="note-b",
            mid=101,
            fields=["Cloze text", "Extra"],
            tags=[],
            did=child_did,
        )
        return parent_did, child_did

    def _export_json(self, col):
        """The real export path: from_collection → JSON serialization."""
        deck = deck_initializer.from_collection(col, "Parent")
        return json.dumps(deck, default=Deck.default_json, sort_keys=True)

    def _to_deck_repr(self, json_str):
        return deck_initializer.from_json(json.loads(json_str))

    def _norm(self, repr_deck):
        """Flatten a Deck representation into comparable data, normalizing
        local numeric ids and mod timestamps (expected to differ)."""
        payload = json.loads(
            json.dumps(repr_deck, default=Deck.default_json, sort_keys=True)
        )
        return _strip_expected_diffs(payload)

    def test_roundtrip_preserves_hierarchy_and_uuids(
        self, realistic_collection, fake_anki_note_class
    ):
        col = realistic_collection
        self._seed(col)
        json_a = self._export_json(col)
        deck_b = self._to_deck_repr(json_a)

        # Same deck tree shape
        assert deck_b.anki_dict["name"] == "Parent"
        assert len(deck_b.children) == 1
        assert deck_b.children[0].flatten()["name"] == "Child"

        # Deck UUIDs survive
        assert deck_b.get_uuid() == "deck-parent"
        assert deck_b.children[0].get_uuid() == "deck-child"

        # Note GUIDs survive
        guids = {n.get_uuid() for n in deck_b.notes}
        assert "note-a" in guids

    def test_roundtrip_preserves_fields_and_tags(
        self, realistic_collection, fake_anki_note_class
    ):
        col = realistic_collection
        self._seed(col)
        deck_b = self._to_deck_repr(self._export_json(col))

        note_a = next(n for n in deck_b.notes if n.get_uuid() == "note-a")
        assert note_a.anki_object_dict["fields"] == ["Front A", "Back A"]
        assert set(note_a.anki_object_dict["tags"]) == {"tag1", "tag2"}

        # note-b is in the child deck
        child = deck_b.children[0]
        note_b = next(n for n in child.notes if n.get_uuid() == "note-b")
        assert note_b.anki_object_dict["fields"] == ["Cloze text", "Extra"]

    def test_roundtrip_preserves_note_models_templates_and_css(
        self, realistic_collection, fake_anki_note_class
    ):
        col = realistic_collection
        self._seed(col)
        deck_b = self._to_deck_repr(self._export_json(col))

        basic_model = deck_b.metadata.models["model-basic"]
        assert basic_model.anki_dict["name"] == "Basic"
        assert basic_model.anki_dict["css"] == ".card { color: blue; }"
        # Field names and order survive
        assert [f["name"] for f in basic_model.anki_dict["flds"]] == ["Front", "Back"]
        assert [t["name"] for t in basic_model.anki_dict["tmpls"]] == ["Card 1"]

    def test_roundtrip_is_semantically_identical(
        self, realistic_collection, fake_anki_note_class
    ):
        """The exported representation and the imported representation must be
        semantically identical (deck tree, UUIDs, notes, models, templates,
        CSS) — normalizing only expected local differences."""
        col = realistic_collection
        self._seed(col)
        deck_a = deck_initializer.from_collection(col, "Parent")
        deck_b = self._to_deck_repr(self._export_json(col))

        assert _repr_summary(deck_a) == _repr_summary(
            deck_b
        ), "Export→import changed semantically meaningful content"

    def test_roundtrip_into_fresh_collection_via_from_json(
        self, realistic_collection, fake_anki_note_class
    ):
        """Import into a *fresh* collection B's representation and re-export."""
        col_a = realistic_collection
        self._seed(col_a)
        deck_a = deck_initializer.from_collection(col_a, "Parent")
        deck_b = self._to_deck_repr(self._export_json(col_a))

        assert _repr_summary(deck_a) == _repr_summary(deck_b)


def _repr_summary(deck):
    """Extract semantically meaningful content from a Deck representation,
    dropping local numeric ids and mod/usn timestamps."""

    def _note_summary(n):
        data = n.anki_object_dict or {}
        return {
            "guid": n.get_uuid(),
            "fields": list(data.get("fields", [])),
            "tags": sorted(data.get("tags", [])),
        }

    return {
        # flatten() normalizes child names to their short (serialized) form
        "name": deck.flatten().get("name"),
        "uuid": deck.get_uuid(),
        "notes": sorted(
            (_note_summary(n) for n in deck.notes), key=lambda x: x["guid"]
        ),
        "children": [_repr_summary(c) for c in deck.children],
        "note_models": sorted(
            (
                {
                    "uuid": m.get_uuid(),
                    "name": m.anki_dict.get("name"),
                    "css": m.anki_dict.get("css"),
                    "flds": [f["name"] for f in m.anki_dict.get("flds", [])],
                    "tmpls": [t.get("name") for t in m.anki_dict.get("tmpls", [])],
                }
                for m in deck.metadata.models.values()
            ),
            key=lambda x: x["uuid"],
        ),
    }
