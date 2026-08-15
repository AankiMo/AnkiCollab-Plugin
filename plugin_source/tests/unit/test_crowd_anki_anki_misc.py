"""Import-smoke and light logic tests for the remaining crowd_anki/anki
modules (hook_vendor, overrides, ui).  These are largely Qt/override glue; the
tripwire in test_core_module_coverage requires at least one reference per
module, and hook_vendor's real hook-registration logic is exercised here."""

from unittest.mock import MagicMock, patch

import crowd_anki.anki.hook_vendor as hook_vendor
import crowd_anki.anki.overrides.cards  # noqa: F401
import crowd_anki.anki.overrides.change_model_dialog  # noqa: F401
import crowd_anki.anki.overrides.decks  # noqa: F401
import crowd_anki.anki.overrides.exporting  # noqa: F401
import crowd_anki.anki.overrides.models  # noqa: F401
import crowd_anki.anki.ui.action_vendor  # noqa: F401
import crowd_anki.anki.ui.utils  # noqa: F401
from crowd_anki.anki.adapters import hook_manager as hook_manager_module


def test_hook_vendor_registers_exporter_hook():
    """HookVendor.setup_exporter_hook must register the exporters hook."""
    vendor = hook_vendor.HookVendor(window=MagicMock(), config=MagicMock())
    vendor.hook_manager = MagicMock()
    vendor.setup_exporter_hook()
    vendor.hook_manager.hook.assert_called_once()
    assert vendor.hook_manager.hook.call_args[0][0] == "exportersList"


def test_hook_vendor_mutable_default_uses_factory():
    """Regression: hook_manager was a mutable dataclass default (import error).
    Each instance must get its own hook manager."""
    a = hook_vendor.HookVendor(window=MagicMock(), config=MagicMock())
    b = hook_vendor.HookVendor(window=MagicMock(), config=MagicMock())
    assert a.hook_manager is not b.hook_manager


def test_overrides_modules_importable():
    # The modules above must all import without raising — this is the smoke.
    assert crowd_anki.anki.overrides.decks is not None
    assert crowd_anki.anki.ui.action_vendor is not None
