"""Shared fixtures for workflow-level integration tests (Phase 3).

These build a *realistic* fake collection that stores decks, models, and notes
in real Python data structures, so the actual AnkiCollab representation code
(``Deck``/``Note``/``NoteModel``/``deck_initializer``) runs against it and we
can assert on the *resulting collection state* — not just that a mock was
called.  The Anki API boundary (``AnkiNote``) is faked with real data, which is
the accepted trade-off for running outside a real Anki instance.
"""

from __future__ import annotations

import uuid as uuid_mod
from collections import namedtuple
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


class FakeAnkiNote:
    """Drop-in for ``anki.notes.Note`` carrying real data.

    Used by ``Note.from_collection`` (patched in as the ``AnkiNote`` binding)
    so exported notes have real GUIDs, fields, tags, and note types.
    """

    def __init__(
        self,
        collection=None,
        id: int = 0,
        mid: int = 1,
        guid: str = "",
        fields: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        mod: int = 0,
    ):
        self.id = id
        # ``AnkiNote(collection, model_dict)`` — the "new note" construction in
        # Deck._batch_process_notes.  The note's real data is filled in later
        # via ``note.anki_object.__dict__.update(anki_object_dict)``.
        if isinstance(id, dict):
            self.id = 0
            self.mid = id.get("id", 1)
            self.guid = ""
            self.fields = []
            self.tags = []
            self.mod = 0
            self._model = dict(id)
            return
        # When constructed from a collection store (as Note.from_collection
        # does), load the stored record and resolve the note type eagerly.
        # Crucially we must NOT retain any reference to the collection as an
        # instance attribute: real AnkiNote stores it privately, and a public
        # attribute would leak into the exported note serialization.
        if (
            collection is not None
            and fields is None
            and hasattr(collection, "_notes")
            and id in collection._notes
        ):
            rec = collection._notes[id]
            self.mid = rec["mid"]
            self.guid = rec["guid"]
            self.fields = list(rec["fields"])
            self.tags = list(rec["tags"])
            self.mod = rec.get("mod", 0)
            model = collection.models.get(self.mid)
            self._model = dict(model) if model else {}
            return
        self.mid = mid
        self.guid = guid
        self.fields = list(fields) if fields else []
        self.tags = list(tags) if tags else []
        self.mod = mod
        self._model = None

    def note_type(self):
        if self._model is None:
            self._model = {}
        return self._model

    def __getitem__(self, key):
        return ""

    def keys(self):
        model = self.note_type() or {}
        return [f["name"] for f in model.get("flds", [])]

    def card_ids(self):
        return []

    def joined_fields(self):
        return "\x1f".join(self.fields)


class RealisticCollection:
    """An in-memory Anki collection that stores decks/models/notes for real.

    Implements the subset of the Anki API surface that AnkiCollab's
    representation layer reads and writes.
    """

    def __init__(self, media_dir: Optional[Path] = None):
        self.media_dir = media_dir
        self._decks: Dict[int, Dict[str, Any]] = {}
        self._models: Dict[int, Dict[str, Any]] = {}
        self._notes: Dict[int, Dict[str, Any]] = {}
        self._next_deck_id = 1
        self._next_note_id = 1

        # ---- decks ----
        def _deck_id(name, create=True):
            for did, d in self._decks.items():
                if d["name"] == name:
                    return did
            if create:
                did = self._next_deck_id
                self._next_deck_id += 1
                self._decks[did] = {
                    "id": did,
                    "name": name,
                    "dyn": False,
                    "crowdanki_uuid": str(uuid_mod.uuid4()),
                }
                return did
            return None

        def _deck_by_name(name):
            for d in self._decks.values():
                if d["name"] == name:
                    return dict(d)
            return None

        def _deck_get(did, default=True):
            if did in self._decks:
                return dict(self._decks[did])
            if default:
                return {"id": did, "name": "Default", "dyn": False}
            return None

        def _deck_save(d):
            self._decks[d["id"]] = dict(d)

        def _deck_children(did):
            parent = self._decks.get(did, {}).get("name", "")
            return [
                (d["name"], d["id"])
                for d in self._decks.values()
                if d["name"].startswith(parent + "::") and d["id"] != did
            ]

        def _deck_all():
            return [dict(d) for d in self._decks.values()]

        _NI = namedtuple("NameAndId", ["name", "id"])

        def _deck_all_names_and_ids():
            return [_NI(d["name"], d["id"]) for d in self._decks.values()]

        def _deck_name(did):
            d = self._decks.get(did)
            return d["name"] if d else ""

        def _deck_name_if_exists(did):
            d = self._decks.get(did)
            return d["name"] if d else None

        def _deck_card_count(did, include_subdecks=False):
            return 0

        def _deck_get_note_ids(did, include_from_dynamic=False):
            # notes are stored with their target deck id
            return [nid for nid, n in self._notes.items() if n.get("did") == did]

        self.decks = MagicMock()
        self.decks.id.side_effect = _deck_id
        self.decks.by_name.side_effect = _deck_by_name
        self.decks.get.side_effect = _deck_get
        self.decks.save.side_effect = _deck_save
        self.decks.children.side_effect = _deck_children
        self.decks.all.side_effect = _deck_all
        self.decks.all_names_and_ids.side_effect = _deck_all_names_and_ids
        self.decks.name.side_effect = _deck_name
        self.decks.name_if_exists.side_effect = _deck_name_if_exists
        self.decks.card_count.side_effect = _deck_card_count
        self.decks.get_note_ids.side_effect = _deck_get_note_ids

        # ---- models ----
        def _model_get(mid):
            m = self._models.get(int(mid))
            return dict(m) if m else None

        def _model_all():
            return [dict(m) for m in self._models.values()]

        def _model_add(m):
            self._models[int(m["id"])] = dict(m)

        def _model_update_dict(m):
            self._models[int(m["id"])] = dict(m)

        def _model_by_name(name):
            for m in self._models.values():
                if m.get("name") == name:
                    return dict(m)
            return None

        def _model_new(name):
            return {
                "id": 0,
                "name": name,
                "flds": [],
                "tmpls": [],
                "css": "",
                "crowdanki_uuid": "",
            }

        self.models = MagicMock()
        self.models.get.side_effect = _model_get
        self.models.all.side_effect = _model_all
        self.models.add.side_effect = _model_add
        self.models.update_dict.side_effect = _model_update_dict
        self.models.by_name.side_effect = _model_by_name
        self.models.new.side_effect = _model_new

        # ---- db ----
        def _db_all(query, *params):
            # Minimal support for "select ... from notes where guid in (...)"
            low = query.lower()
            if "from notes" in low and "guid" in low:
                guids = [p for p in params if isinstance(p, str)]
                if not guids:
                    guids = [str(p) for p in params]
                out = []
                for nid, n in self._notes.items():
                    if n["guid"] in guids:
                        out.append((n["guid"], nid))
                return out
            if "from cards" in low:
                return []
            return []

        def _db_scalar(query, *params):
            return 0

        def _db_list(query, *params):
            return []

        def _db_first(query, *params):
            return None

        self.db = MagicMock()
        self.db.all.side_effect = _db_all
        self.db.scalar.side_effect = _db_scalar
        self.db.list.side_effect = _db_list
        self.db.first.side_effect = _db_first

        # ---- media ----
        self.media = MagicMock()
        self.media.dir.return_value = str(media_dir) if media_dir else ""
        self.media.files_in_str.return_value = []

        # ---- note operations ----
        self.add_note = MagicMock()
        self.add_notes = MagicMock()
        self.update_notes = MagicMock()
        self.get_note = MagicMock()
        self.remove_notes = MagicMock()
        self.set_deck = MagicMock()
        self.sched = MagicMock()

    # --- helpers to seed / inspect ---
    def add_deck(self, name, deck_uuid=None, did=None):
        did = did or self._next_deck_id
        self._next_deck_id = max(self._next_deck_id, did + 1)
        self._decks[did] = {
            "id": did,
            "name": name,
            "dyn": False,
            "crowdanki_uuid": deck_uuid or str(uuid_mod.uuid4()),
        }
        return did

    def add_model(self, model_dict):
        mid = int(model_dict.get("id") or (max(self._models, default=0) + 1))
        model_dict["id"] = mid
        self._models[mid] = dict(model_dict)
        return mid

    def add_note_record(self, guid, mid, fields, tags, did=1, nid=None, mod=0):
        nid = nid or self._next_note_id
        self._next_note_id = max(self._next_note_id, nid + 1)
        self._notes[nid] = {
            "id": nid,
            "guid": guid,
            "mid": mid,
            "fields": list(fields),
            "tags": list(tags),
            "did": did,
            "mod": mod,
        }
        return nid

    def note(self, nid) -> FakeAnkiNote:
        rec = self._notes[nid]
        return FakeAnkiNote(
            collection=self,
            id=rec["id"],
            mid=rec["mid"],
            guid=rec["guid"],
            fields=rec["fields"],
            tags=rec["tags"],
            mod=rec["mod"],
        )

    def deck_names(self):
        return [d["name"] for d in self._decks.values()]

    def note_records(self):
        return list(self._notes.values())

    def model_ids(self):
        return list(self._models.keys())


@pytest.fixture
def realistic_collection(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    return RealisticCollection(media_dir=media)


@pytest.fixture
def mw_mock(monkeypatch):
    """A mock aqt.mw for integration tests that touch the collection.

    Patches both ``aqt.mw`` and the module-level ``mw`` binding in
    ``export_manager`` (where the media-reference workflow lives).
    """
    from tests.mocks import create_mock_mw

    mock = create_mock_mw()
    monkeypatch.setattr("aqt.mw", mock)
    import export_manager as export_mod

    monkeypatch.setattr(export_mod, "mw", mock)
    return mock


@pytest.fixture
def fake_anki_note_class(monkeypatch):
    """Patch the AnkiNote bindings used by the representation layer to
    FakeAnkiNote — both ``note.py`` (export/from_collection) and ``deck.py``
    (import note construction) reference it."""
    import crowd_anki.representation.note as note_mod
    import crowd_anki.representation.deck as deck_mod

    monkeypatch.setattr(note_mod, "AnkiNote", FakeAnkiNote)
    monkeypatch.setattr(deck_mod, "AnkiNote", FakeAnkiNote)
    return FakeAnkiNote
