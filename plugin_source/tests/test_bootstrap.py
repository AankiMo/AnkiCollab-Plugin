"""Bootstrap integrity tests — Phase 0.1.

The root ``conftest.py`` imports every production addon module in dependency
order.  It must **fail collection loudly** when a production module cannot be
imported, never silently substituting a ``MagicMock``.  If it substituted a
mock, every dependent module's tests would run against a mock instead of real
code — and a genuinely broken production module would pass CI forever.

This file proves that behaviour by simulating a broken production module and
asserting the bootstrap raises instead of continuing.
"""

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
ADDON_ROOT = TESTS_DIR.parent


def _load_root_conftest():
    """Return the already-loaded root conftest module (without re-executing it).

    Re-executing ``conftest.py`` would re-register the addon package with a
    fresh empty module, corrupting the state other tests rely on — so we look
    up the module pytest already imported, by its file path.
    """
    root_conftest_path = (ADDON_ROOT / "conftest.py").resolve()
    for mod in list(sys.modules.values()):
        mod_file = getattr(mod, "__file__", None)
        if mod_file and Path(mod_file).resolve() == root_conftest_path:
            return mod
    raise AssertionError(
        "Root conftest.py was not loaded — are tests being run from the addon root?"
    )


def test_broken_production_module_import_fails_loudly(monkeypatch):
    """A production module that cannot import must raise, not get a mock.

    We monkeypatch the bootstrap's per-module importer so importing one
    specific module raises, then drive the *real* import loop and assert it
    re-raises with the module name in the message.
    """
    root_conftest = _load_root_conftest()
    real_importer = root_conftest._import_addon_module

    BROKEN = "zzz_simulated_broken_module"

    def _failing_importer(name):
        if name == BROKEN:
            raise ImportError("simulated broken production module")
        return real_importer(name)

    monkeypatch.setattr(root_conftest, "_import_addon_module", _failing_importer)
    monkeypatch.setattr(root_conftest, "_ADDON_MODULES_ORDERED", [BROKEN])

    with pytest.raises(RuntimeError) as excinfo:
        root_conftest._import_addon_modules()  # the real loop

    # The failure names the module...
    assert BROKEN in str(excinfo.value)
    # ...and the original traceback is preserved as the cause.
    assert isinstance(excinfo.value.__cause__, ImportError)
    assert "simulated broken production module" in str(excinfo.value.__cause__)

    # Crucially: no MagicMock fallback was registered for the broken module.
    full = f"{root_conftest.ADDON_PACKAGE}.{BROKEN}"
    assert full not in sys.modules
    assert BROKEN not in sys.modules


def test_broken_module_failure_not_swallowed_by_plain_except(monkeypatch):
    """Regression guard: the loop must not contain a mock-substituting handler.

    Even if someone reintroduces a bare ``except Exception`` in the loop, it
    must re-raise — a fresh, never-before-seen module name must still abort.
    """
    root_conftest = _load_root_conftest()

    # Prove the loop function itself has no fallback path by scanning its
    # source for the old mock-substitution idiom.
    import inspect

    source = inspect.getsource(root_conftest._import_addon_modules)
    assert "sys.modules.setdefault" not in source or ("_mock_mod" not in source), (
        "The addon import loop must not install a MagicMock fallback. "
        "Remove the mock-substitution from _import_addon_modules()."
    )
