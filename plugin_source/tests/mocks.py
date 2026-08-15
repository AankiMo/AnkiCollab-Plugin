"""Anki mock helpers.

Provides ``create_mock_mw()`` which returns a fully wired MagicMock of
``aqt.mw`` — the global Anki main-window object that almost every addon
module touches.  Also supplies lightweight stand-ins for ``anki.notes.Note``,
``anki.models.NotetypeDict``, ``anki.decks.DeckId``, etc.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, PropertyMock, patch

# ---------------------------------------------------------------------------
# Lightweight Anki type stand-ins
# ---------------------------------------------------------------------------


class FakeNote:
    """Minimal stand-in for ``anki.notes.Note``."""

    def __init__(
        self,
        mid: int = 1,
        guid: str = "abc123",
        id: int = 0,
        fields: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ):
        self.mid = mid
        self.guid = guid
        self.id = id
        self.fields = fields or ["front", "back"]
        self.tags = tags or []
        self.note_type = MagicMock(return_value={"id": mid, "name": "Basic"})

    def __getitem__(self, key: str) -> str:
        return ""

    def __setitem__(self, key: str, value: str) -> None:
        pass

    def string_tags(self) -> str:
        return " ".join(self.tags)


class FakeCard:
    """Minimal stand-in for ``anki.cards.Card``."""

    def __init__(self, nid: int = 0, did: int = 1, id: int = 0):
        self.nid = nid
        self.did = did
        self.id = id


class FakeCol:
    """Minimal stand-in for ``anki.collection.Collection``.

    Wraps a MagicMock so callers can set return values on sub-attributes
    (``col.decks.get()``, ``col.models.get()``, etc.) while still having
    sensible defaults.
    """

    def __init__(self) -> None:
        self.models = MagicMock()
        self.decks = MagicMock()
        self.tags = MagicMock()
        self.db = MagicMock()
        self.media = MagicMock()
        self.media.dir.return_value = ""
        self.conf = {}

        # get_note returns a FakeNote by default
        self.get_note = MagicMock(return_value=FakeNote())
        self.find_notes = MagicMock(return_value=[])
        self.find_cards = MagicMock(return_value=[])
        self.remove_notes = MagicMock()
        self.update_note = MagicMock()
        self.add_note = MagicMock(return_value=1)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Main mock builder
# ---------------------------------------------------------------------------


def create_mock_mw(
    *,
    config: Optional[Dict[str, Any]] = None,
    col: Optional[Any] = None,
    media_dir: Optional[str | Path] = None,
) -> MagicMock:
    """Build a fully wired ``MagicMock`` mimicking ``aqt.mw``.

    Parameters
    ----------
    config:
        The dict that ``mw.addonManager.getConfig(...)`` should return.
        Defaults to ``{}``.
    col:
        A replacement collection object.  If *None*, a ``FakeCol`` is used.
    media_dir:
        Path returned by ``mw.col.media.dir()``.  Defaults to ``""``.

    Returns
    -------
    MagicMock
        Drop-in replacement for ``aqt.mw``.
    """
    if config is None:
        config = {}
    if col is None:
        col = FakeCol()
    if media_dir is not None:
        col.media.dir.return_value = str(media_dir)

    mw = MagicMock()
    mw.col = col

    # addon manager --------------------------------------------------------
    addon_mgr = MagicMock()
    _config_store: Dict[str, Any] = dict(config)  # mutable copy

    def _get_config(addon_id: Any = None) -> Dict[str, Any]:
        return _config_store

    def _write_config(addon_id: Any, cfg: Dict[str, Any]) -> None:
        _config_store.clear()
        _config_store.update(cfg)

    addon_mgr.getConfig = MagicMock(side_effect=_get_config)
    addon_mgr.writeConfig = MagicMock(side_effect=_write_config)
    # Return the actual addon package name instead of hardcoded ID
    from pathlib import Path

    _addon_root = Path(__file__).resolve().parent.parent
    addon_mgr.addonFromModule = MagicMock(return_value=_addon_root.name)
    addon_mgr.addonsFolder = MagicMock(return_value="")
    mw.addonManager = addon_mgr

    # progress / taskman ---------------------------------------------------
    mw.progress = MagicMock()
    mw.progress.want_cancel.return_value = False
    mw.taskman = MagicMock()
    mw.taskman.run_on_main = MagicMock(side_effect=lambda fn: fn())
    mw.taskman.with_progress = MagicMock()

    # reviewer / state ----------------------------------------------------
    mw.reviewer = MagicMock()
    mw.state = "overview"

    return mw


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


def patch_aqt_mw(mw_mock: MagicMock):
    """Return a context-manager / decorator that patches ``aqt.mw`` globally.

    Usage::

        with patch_aqt_mw(my_mock):
            from utils import DeckManager
            ...
    """
    return patch("aqt.mw", mw_mock)


def install_fake_aqt_module():
    """Create a minimal ``aqt`` package in ``sys.modules`` so that addon
    code can be imported outside a real Anki environment.

    This is called once from the unit conftest so you rarely need it
    directly.
    """
    for mod_name in (
        "aqt",
        "aqt.qt",
        "aqt.utils",
        "aqt.gui_hooks",
        "aqt.operations",
        "aqt.operations.note",
        "aqt.browser",
        "aqt.editor",
        "aqt.reviewer",
        "aqt.addcards",
        "aqt.sound",
        "aqt.theme",
    ):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

    for mod_name in (
        "anki",
        "anki.collection",
        "anki.consts",
        "anki.decks",
        "anki.errors",
        "anki.hooks",
        "anki.models",
        "anki.notes",
        "anki.cards",
        "anki.utils",
        "anki.sound",
    ):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

    # Make sure aqt.mw is a MagicMock that can be re-patched per-test
    aqt_mod = sys.modules["aqt"]
    if not hasattr(aqt_mod, "mw") or aqt_mod.mw is None:
        aqt_mod.mw = MagicMock()
