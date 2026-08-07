"""Validates user-configured keyboard shortcuts against known collisions
with Anki built-in shortcuts, common add-on shortcuts, and system-level
shortcuts.

All shortcut strings use QKeySequence.PortableText format, which is
platform-independent (e.g. "Ctrl+Alt+U" on all platforms, with "Meta"
representing Cmd on macOS and the Windows key on Windows/Linux).

Only 2+ modifier shortcuts are tracked here; single-modifier shortcuts
are already rejected by the existing modifier-count rule in menu.py.

Sources:
  - ankitects/anki qt/aqt/main.py (setupKeys, setupMenus, _shortcutKeys)
  - ankitects/anki qt/aqt/reviewer.py (reviewer _shortcutKeys)
  - ankitects/anki qt/aqt/browser/browser.py (browser setupMenus)
  - Anki manual (docs.ankiweb.net)
  - KeyCombiner Anki collection (keycombiner.com/collections/anki/)
  - macOS Human Interface Guidelines
  - Windows / Linux desktop environment defaults
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from anki.utils import is_mac, is_win
from aqt.qt import QKeySequence


class Severity(Enum):
    """Severity of a shortcut collision."""
    BLOCKED = "blocked"   # Cannot be saved — hard error
    WARNING = "warning"   # Can be saved after user confirmation


class Context(Enum):
    """The Anki window context in which the shortcut will be active."""
    MAIN_WINDOW = "main"      # Deck overview / reviewer → "Update Decks" shortcut
    BROWSER = "browser"        # Browser window → "Bulk Suggest" shortcut


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating a shortcut against known collisions."""
    is_valid: bool
    severity: Severity | None          # None if valid (no collision at all)
    message: str                       # Human-readable explanation
    conflicting_action: str = ""       # What the conflicting shortcut does


# ===========================================================================
# Anki built-in shortcuts (2+ modifiers only)
# ===========================================================================

# Reviewer shortcuts — active in the main window study state
_ANKI_REVIEWER_BLOCKED: Dict[str, str] = {
    "Ctrl+Alt+N":       "Anki: Forget current card",
    "Ctrl+Alt+E":       "Anki: Create copy of current card",
    "Ctrl+Alt+I":       "Anki: Show previous card info",
    "Ctrl+Shift+D":     "Anki: Set due date",
}

# Main-window menu / global shortcuts (deck overview + all states)
_ANKI_MAIN_BLOCKED: Dict[str, str] = {
    "Ctrl+Shift+I":     "Anki: Import file",
    "Ctrl+Shift+E":     "Anki: Export",
    "Ctrl+Shift+N":     "Anki: Manage Note Types",
    "Ctrl+Shift+A":     "Anki: Manage Add-ons",
    "Ctrl+Shift+P":     "Anki: Switch Profile",
    "Ctrl+Shift+B":     "Anki: Open Browser",
    "Ctrl+Shift+Y":     "Anki: Sync",
    "Ctrl+Alt+T":       "Anki: Toggle cards/notes mode",
}

# All blocked in the main window (reviewer + global)
_ANKI_MAIN_ALL_BLOCKED: Dict[str, str] = {
    **_ANKI_REVIEWER_BLOCKED,
    **_ANKI_MAIN_BLOCKED,
}

# Browser-specific shortcuts
_ANKI_BROWSER_BLOCKED: Dict[str, str] = {
    "Ctrl+Alt+T":           "Anki Browser: Toggle cards/notes mode",
    "Ctrl+Alt+F":           "Anki Browser: Find duplicates",
    "Ctrl+Shift+K":         "Anki Browser: Remove tags",
    "Ctrl+Shift+D":         "Anki Browser: Change note type / model",
    "Ctrl+Shift+J":         "Anki Browser: Unsuspend card(s)",
    "Ctrl+Shift+R":         "Anki Browser: Reset card(s)",
    "Ctrl+Shift+C":         "Anki Browser: Copy (browser list)",
    "Ctrl+Shift+M":         "Anki Browser: Add card type",
    "Ctrl+Shift+N":         "Anki Browser: Add field",
    "Ctrl+Shift+F":         "Anki Browser: Find and replace",
    "Ctrl+Shift+G":         "Anki Browser: Find previous",
    "Ctrl+Shift+1":         "Anki Browser: Toggle sidebar",
    "Ctrl+Shift+P":         "Anki Browser: Toggle preview pane",
    "Ctrl+Alt+Shift+T":     "Anki Browser: Suspend all cards",
}

# ===========================================================================
# System-level shortcuts (2+ modifiers, platform-specific)
# These are typically intercepted by the OS before Qt ever sees them,
# making them dead keys for add-on shortcuts.
# ===========================================================================

_SYSTEM_BLOCKED: Dict[str, str] = {}

if is_mac:
    _SYSTEM_BLOCKED.update({
        "Meta+Shift+3":     "macOS: Screenshot (full screen)",
        "Meta+Shift+4":     "macOS: Screenshot (selection)",
        "Meta+Shift+5":     "macOS: Screenshot / recording panel",
        "Meta+Ctrl+Q":      "macOS: Lock Screen",
        "Meta+Ctrl+F":      "macOS: Toggle full screen",
    })

if is_win:
    _SYSTEM_BLOCKED.update({
        "Ctrl+Alt+Del":     "Windows: Security screen",
        "Ctrl+Shift+Esc":   "Windows: Task Manager",
        # Note: AltGr (right Alt) triggers Ctrl+Alt on Windows keyboards.
        # Anki already works around this (qt/aqt/__init__.py), but
        # Ctrl+Alt+<letter> shortcuts are still risky for international users.
    })

if not is_mac and not is_win:
    # Linux — common desktop environment defaults
    _SYSTEM_BLOCKED.update({
        "Ctrl+Alt+Del":     "Linux: Logout / shutdown dialog",
        "Ctrl+Alt+L":       "Linux: Lock screen (KDE / GNOME)",
        "Ctrl+Alt+T":       "Linux: Open terminal (GNOME / Ubuntu)",
        "Ctrl+Alt+Esc":     "Linux: Kill window / System monitor (KDE)",
        "Ctrl+Alt+F1":      "Linux: Switch to virtual console",
        "Ctrl+Alt+F2":      "Linux: Switch to virtual console",
        "Ctrl+Alt+F3":      "Linux: Switch to virtual console",
        "Ctrl+Alt+F4":      "Linux: Switch to virtual console",
        "Ctrl+Alt+F5":      "Linux: Switch to virtual console",
        "Ctrl+Alt+F6":      "Linux: Switch to virtual console",
        "Ctrl+Alt+F7":      "Linux: Switch to virtual console",
        "Ctrl+Alt+F8":      "Linux: Switch to virtual console",
    })

# ===========================================================================
# Common add-on shortcuts (WARNING level — user can override)
# These are popular shortcuts used by well-known Anki add-ons.
# ===========================================================================

_ADDON_WARNING: Dict[str, str] = {
    "Ctrl+Alt+O":       "the Image Occlusion Enhanced add-on",
    "Ctrl+Alt+S":       "the Review Heatmap / Stats add-on",
    "Ctrl+Alt+R":       "a Reschedule / Reset add-on",
    "Ctrl+Alt+P":       "a Preview / Card Info add-on",
    "Ctrl+Alt+L":       "a Layout / Card Info add-on",
    "Ctrl+Alt+M":       "a Media import add-on",
    "Ctrl+Alt+D":       "a Deck-related add-on",
    "Ctrl+Alt+G":       "a Graph / Stats add-on",
    "Ctrl+Alt+B":       "a Backup / Browse add-on",
    "Ctrl+Shift+O":     "a Deck overlay add-on",
    "Ctrl+Shift+T":     "a Tag-related add-on",
    "Ctrl+Shift+L":     "a Layout / Cloze add-on",
    "Ctrl+Shift+S":     "a Save / Sync add-on",
    "Ctrl+Shift+H":     "a Heatmap / Highlight add-on",
}

# ===========================================================================
# Internal helpers
# ===========================================================================

def _extract_first_combination(seq: QKeySequence) -> str:
    """Return the first key combination in portable text format.

    Multi-key sequences like "Ctrl+Alt+U, Ctrl+Alt+I" only have their
    first combination validated (the secondary is a fallback).
    """
    text = seq.toString(QKeySequence.SequenceFormat.PortableText)
    return text.split(",", 1)[0].strip()


def _modifier_count(combo: str) -> int:
    """Count how many modifier keys appear in a portable-format combo string."""
    modifiers = {"Ctrl", "Alt", "Shift", "Meta"}
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    return sum(1 for p in parts if p in modifiers)


# ===========================================================================
# Public API
# ===========================================================================

def validate_shortcut(seq: QKeySequence, context: Context) -> ValidationResult:
    """Validate a shortcut against known collisions.

    Args:
        seq: The QKeySequence from a QKeySequenceEdit.
        context: The Anki window context where the shortcut will be active.

    Returns:
        ValidationResult where:
        - is_valid=False, severity=BLOCKED → cannot be saved (show error)
        - is_valid=True,  severity=WARNING → can be saved after confirmation
        - is_valid=True,  severity=None    → no collision, safe to save
    """
    # Empty shortcut is always valid (no shortcut configured)
    if seq.isEmpty():
        return ValidationResult(True, None, "")

    combo = _extract_first_combination(seq)

    # Must have at least 2 modifier keys (existing rule, kept here as first gate)
    if _modifier_count(combo) < 2:
        return ValidationResult(
            False,
            Severity.BLOCKED,
            f"'{combo}' must use at least two modifier keys "
            f"(e.g. Ctrl+Alt+U). Single-modifier shortcuts are too likely "
            f"to conflict with Anki's built-in keys.",
        )

    # ---- Build the effective blacklists for this context ----
    blocked: Dict[str, str] = dict(_SYSTEM_BLOCKED)
    warning: Dict[str, str] = dict(_ADDON_WARNING)

    if context == Context.MAIN_WINDOW:
        blocked.update(_ANKI_MAIN_ALL_BLOCKED)
    elif context == Context.BROWSER:
        blocked.update(_ANKI_BROWSER_BLOCKED)

    # ---- Check BLOCKED (hard rejection) ----
    if combo in blocked:
        return ValidationResult(
            False,
            Severity.BLOCKED,
            f"'{combo}' conflicts with {blocked[combo]}.\n\n"
            f"Please choose a different shortcut.",
            blocked[combo],
        )

    # ---- Check WARNING (user confirmation) ----
    if combo in warning:
        return ValidationResult(
            True,  # technically valid, but needs confirmation
            Severity.WARNING,
            f"'{combo}' may conflict with {warning[combo]}.\n\n"
            f"Do you want to use it anyway?",
            warning[combo],
        )

    # ---- No conflicts ----
    return ValidationResult(True, None, "")
