"""Root-level conftest — loaded FIRST by pytest.

Prevents the addon's ``__init__.py`` (which does ``from .main import *``)
from being imported by pytest's package-collection mechanism.
We register a dummy package module in sys.modules before pytest can
attempt to import it.
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ── SKIP_INIT pattern ──────────────────────────────────────────────────
os.environ["SKIP_INIT"] = "1"

# ── Determine paths ───────────────────────────────────────────────────
ADDON_ROOT = Path(__file__).resolve().parent
ADDON_PACKAGE = ADDON_ROOT.name  # "1957538407"
ADDONS_DIR = str(ADDON_ROOT.parent)

# ── Fake aqt / anki / sentry_sdk modules ──────────────────────────────
_FAKE_MODULES = [
    "aqt",
    "aqt.qt",
    "aqt.utils",
    "aqt.gui_hooks",
    "aqt.operations",
    "aqt.operations.note",
    "aqt.operations.tag",
    "aqt.browser",
    "aqt.editor",
    "aqt.reviewer",
    "aqt.addcards",
    "aqt.sound",
    "aqt.theme",
    "aqt.errors",
    "aqt.dialogs",
    "aqt.emptycards",
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
    "anki.exporting",
    "sentry_sdk",
]

for _mod_name in _FAKE_MODULES:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# --- Fix anki.utils.point_version to return an integer ---
# note.py calls ``point_version()`` at module level and compares the result
# to integer constants.  A MagicMock would fail the ``>=`` comparison.
_anki_utils = sys.modules["anki.utils"]
_anki_utils.point_version = MagicMock(return_value=250100)  # pretend Anki 25.01
_anki_utils.is_win = True
_anki_utils.join_fields = lambda fields: "\x1f".join(fields)
_anki_utils.split_fields = lambda s: s.split("\x1f")
_anki_utils.ids2str = lambda ids: "(%s)" % ",".join(str(i) for i in ids)

# --- Fake 'functional' (PyFunctional) package used by crowd_anki/utils/uuid.py ---
if "functional" not in sys.modules:
    _functional_mock = types.ModuleType("functional")

    # seq() should iterate over a list and support .find()
    class _FakeSeq:
        def __init__(self, iterable=None):
            self._data = list(iterable) if iterable else []

        def find(self, predicate):
            for item in self._data:
                if predicate(item):
                    return item
            return None

        def __iter__(self):
            return iter(self._data)

    _functional_mock.seq = _FakeSeq
    sys.modules["functional"] = _functional_mock

# --- Fake anki.models types used by deck.py ---
_anki_models = sys.modules.get("anki.models")
if _anki_models is None:
    _anki_models = MagicMock()
    sys.modules["anki.models"] = _anki_models
for _sym in ("ChangeNotetypeRequest", "NoteType", "NotetypeDict", "NotetypeId"):
    if not hasattr(_anki_models, _sym) or isinstance(
        getattr(_anki_models, _sym), MagicMock
    ):
        setattr(_anki_models, _sym, MagicMock())

# --- Fake anki.collection.AddNoteRequest used conditionally by note.py ---
_anki_collection = sys.modules.get("anki.collection")
if _anki_collection is None:
    _anki_collection = MagicMock()
    sys.modules["anki.collection"] = _anki_collection
if not hasattr(_anki_collection, "AddNoteRequest") or isinstance(
    getattr(_anki_collection, "AddNoteRequest"), MagicMock
):
    setattr(_anki_collection, "AddNoteRequest", MagicMock())

# Wire up aqt.qt symbols used via ``from aqt.qt import *``
_qt_mod = sys.modules["aqt.qt"]
# qtmajor must be a real int — import_ui.py does ``if qtmajor > 5:``
_qt_mod.qtmajor = 6

# --- Stub classes that can be used as base classes in addon code ---
# MagicMock *instances* cannot serve as base classes in Python 3, so we
# provide lightweight classes for the Qt types that addon modules inherit from.


class _StubQThread:
    """Minimal stub for QThread so subclasses can define class bodies."""

    def __init__(self, *a, **kw):
        pass

    def start(self):
        pass

    def isRunning(self):
        return False


class _StubQDialog:
    """Minimal stub for QDialog."""

    def __init__(self, *a, **kw):
        pass

    def setWindowTitle(self, *a):
        pass

    def resize(self, *a):
        pass

    def exec(self):
        pass

    def accept(self):
        pass

    def close(self):
        pass

    def raise_(self):
        pass

    def activateWindow(self):
        pass


class _StubQWebEnginePage:
    """Minimal stub for QWebEnginePage."""

    def __init__(self, *a, **kw):
        pass

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        return True

    def runJavaScript(self, *a):
        pass


class _StubQWebEngineView:
    """Minimal stub for QWebEngineView."""

    def __init__(self, *a, **kw):
        pass

    def setPage(self, *a):
        pass

    def page(self):
        return None

    loadFinished = MagicMock()

    def load(self, *a):
        pass


def _stub_pyqtSignal(*args, **kwargs):
    """Return a MagicMock descriptor that acts like pyqtSignal."""
    return MagicMock()


_qt_mod.QThread = _StubQThread
_qt_mod.QDialog = _StubQDialog
_qt_mod.QWebEnginePage = _StubQWebEnginePage
_qt_mod.QWebEngineView = _StubQWebEngineView
_qt_mod.pyqtSignal = _stub_pyqtSignal

for _sym in (
    "QVBoxLayout",
    "QHBoxLayout",
    "QGroupBox",
    "QLabel",
    "Qt",
    "QWidget",
    "QToolButton",
    "QLineEdit",
    "QPushButton",
    "QListWidget",
    "QAbstractItemView",
    "QShortcut",
    "QKeySequence",
    "QTextEdit",
    "QCheckBox",
    "QApplication",
    "QMessageBox",
    "QMenu",
    "QAction",
    "QtWidgets",
    "QFont",
    "QSize",
    "QListWidgetItem",
    "QIcon",
    "QPixmap",
    "QColor",
    "QSizePolicy",
    "QSpacerItem",
    "QHeaderView",
    "QTableWidget",
    "QTableWidgetItem",
    "QUrl",
    "QTimer",
    "QTextBrowser",
):
    if not hasattr(_qt_mod, _sym):
        setattr(_qt_mod, _sym, MagicMock())

sys.modules["aqt"].mw = MagicMock()

# ── Register addon package WITHOUT running __init__.py ────────────────
if ADDONS_DIR not in sys.path:
    sys.path.insert(0, ADDONS_DIR)
if str(ADDON_ROOT) not in sys.path:
    sys.path.insert(0, str(ADDON_ROOT))

# Create a lightweight package module
_pkg = types.ModuleType(ADDON_PACKAGE)
_pkg.__path__ = [str(ADDON_ROOT)]
_pkg.__package__ = ADDON_PACKAGE
_pkg.__file__ = str(ADDON_ROOT / "__init__.py")
sys.modules[ADDON_PACKAGE] = _pkg

# Also register under the names pytest may try during import_path
# (pytest with importlib mode may compute "__init__" as the module name
# since __init__.py is at the rootdir)
sys.modules[f"{ADDON_PACKAGE}.__init__"] = _pkg
sys.modules["__init__"] = _pkg


# ── Pre-register 'main' as MagicMock ──────────────────────────────────
# main.py has heavy side effects and circular deps; register it as a
# MagicMock so that ``from . import main`` in other submodules resolves
# without triggering the real file.
_main_mock = MagicMock()
_main_full = f"{ADDON_PACKAGE}.main"
sys.modules[_main_full] = _main_mock
sys.modules["main"] = _main_mock
setattr(_pkg, "main", _main_mock)

# ── Import addon submodules (dependency order) ────────────────────────
import importlib


def _import_addon_module(name: str):
    """Import addon submodule by name and register under both
    ``{ADDON_PACKAGE}.{name}`` and ``{name}`` in sys.modules.
    """
    full = f"{ADDON_PACKAGE}.{name}"
    if full not in sys.modules:
        mod = importlib.import_module(f".{name}", package=ADDON_PACKAGE)
        sys.modules[full] = mod
    sys.modules[name] = sys.modules[full]
    # Attach to package so relative imports in other submodules work
    parts = name.split(".")
    target = _pkg
    for i, part in enumerate(parts[:-1]):
        sub_full = f"{ADDON_PACKAGE}.{'.'.join(parts[:i+1])}"
        target = sys.modules.get(sub_full, target)
    setattr(target, parts[-1], sys.modules[full])
    return sys.modules[full]


_ADDON_MODULES_ORDERED = [
    "var_defs",
    "utils",
    "sentry_integration",
    "auth_manager",
    "api_client",
    "identifier",
    "thread",
    "media_exporter",
    "media_manager",
    "media_progress_indicator",
    "media_optimizer",
    "stats",
    "ui",
    "ui.__init__",
    "ui.colors",
    "dialogs",
    "crowd_anki",
    "crowd_anki.__init__",
    "crowd_anki.utils",
    "crowd_anki.utils.__init__",
    "crowd_anki.utils.constants",
    "crowd_anki.utils.uuid",
    "crowd_anki.utils.disambiguate_uuids",
    "crowd_anki.utils.notifier",
    "crowd_anki.utils.utils",
    "crowd_anki.utils.deckconf",
    "crowd_anki.utils.filesystem",
    "crowd_anki.utils.filesystem.__init__",
    "crowd_anki.utils.filesystem.name_sanitizer",
    "crowd_anki.representation",
    "crowd_anki.representation.__init__",
    "crowd_anki.representation.json_serializable",
    "crowd_anki.representation.note_model",
    "crowd_anki.representation.note",
    "crowd_anki.representation.deck_config",
    "crowd_anki.representation.deck",
    "crowd_anki.representation.deck_initializer",
    "crowd_anki.representation.benchmarking",
    "crowd_anki.config",
    "crowd_anki.config.__init__",
    "crowd_anki.config.config_settings",
    "crowd_anki.anki",
    "crowd_anki.anki.__init__",
    "crowd_anki.anki.adapters",
    "crowd_anki.anki.adapters.__init__",
    "crowd_anki.anki.adapters.anki_deck",
    "crowd_anki.anki.adapters.deck_manager",
    "crowd_anki.anki.adapters.file_provider",
    "crowd_anki.anki.adapters.note_model_file_provider",
    "crowd_anki.anki.adapters.hook_manager",
    "crowd_anki.export",
    "crowd_anki.export.__init__",
    "crowd_anki.export.note_sorter",
    "crowd_anki.importer",
    "crowd_anki.importer.__init__",
    "crowd_anki.importer.import_dialog",
    "export_manager",
    "import_manager",
    "menu",
    "hooks",
    "gear_menu_setup",
    "notifications_center",
]

for _name in _ADDON_MODULES_ORDERED:
    try:
        _import_addon_module(_name)
    except Exception as _exc:
        # Register a MagicMock fallback so dependents don't cascade-fail
        _full = f"{ADDON_PACKAGE}.{_name}"
        _mock_mod = MagicMock()
        sys.modules.setdefault(_full, _mock_mod)
        sys.modules.setdefault(_name, _mock_mod)


# Tell pytest not to try collecting the addon's own files as tests
collect_ignore_glob = [
    "main.py",
    "menu.py",
    "hooks.py",
    "dialogs.py",
    "export_manager.py",
    "import_manager.py",
    "media_manager.py",
    "auth_manager.py",
    "identifier.py",
    "stats.py",
    "thread.py",
    "utils.py",
    "var_defs.py",
    "sentry_integration.py",
    "media_exporter.py",
    "media_export.py",
    "media_import.py",
    "media_optimizer.py",
    "media_progress_indicator.py",
    "gear_menu_setup.py",
    "notifications_center.py",
    "crowd_anki/*",
    "ui/*",
    "__pycache__/*",
    "dist/*",
]
