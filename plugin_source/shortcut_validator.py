
# More extensive shortcut validation (includes known collisions) now lives in a separate module
# Only 2+ modifier shortcuts are tracked here since single-modifier shortcuts are not validated in any case

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from anki.utils import is_mac, is_win
from aqt.qt import QKeySequence


class Severity(Enum):
    # Severity of a shortcut collision.
    BLOCKED = "blocked"   # Cannot be saved — hard error
    WARNING = "warning"   # Can be saved after user confirmation


class Context(Enum):
    # The Anki window context in which the shortcut will be active.
    MAIN_WINDOW = "main"
    BROWSER = "browser"


@dataclass(frozen=True)
class ValidationResult:
    # Result of validation
    is_valid: bool
    severity: Severity | None          
    message: str                       
    conflicting_action: str = ""       



# Main-window blocked shortcuts (deck overview + reviewer states)
_ANKI_MAIN_BLOCKED: Dict[str, str] = {
    "Ctrl+Alt+N":       "Anki: Forget current card",
    "Ctrl+Alt+E":       "Anki: Create copy of current card",
    "Ctrl+Alt+I":       "Anki: Show previous card info",
    "Ctrl+Shift+D":     "Anki: Set due date",
    "Ctrl+Shift+I":     "Anki: Import file",
    "Ctrl+Shift+E":     "Anki: Export",
    "Ctrl+Shift+A":     "Anki: Manage Add-ons",
    "Ctrl+Shift+N":     "Anki: Manage Note Types",
    "Ctrl+Shift+P":     "Anki: Switch Profile",
}

# Browser-specific shortcuts
_ANKI_BROWSER_BLOCKED: Dict[str, str] = {
    "Ctrl+Alt+T":           "Anki Browser: Toggle cards/notes mode",
    "Ctrl+Alt+F":           "Anki Browser: Find duplicates",
    "Ctrl+Shift+K":         "Anki Browser: Remove tags",
    "Ctrl+Shift+D":         "Anki Browser: Change note type / model",
    "Ctrl+Shift+J":         "Anki Browser: Unsuspend card(s)",
    "Ctrl+Shift+R":         "Anki Browser: Reset card(s)",
    "Ctrl+Shift+C":         "Anki Browser: Copy (card list) / Cloze deletion (editor)",
    "Ctrl+Shift+M":         "Anki Browser: Add card type",
    "Ctrl+Shift+N":         "Anki Browser: Add field",
    "Ctrl+Shift+F":         "Anki Browser: Find and replace",
    "Ctrl+Shift+G":         "Anki Browser: Find previous",
    "Ctrl+Shift+1":         "Anki Browser: Toggle sidebar",
    "Ctrl+Shift+P":         "Anki Browser: Toggle preview pane",
    "Ctrl+Alt+Shift+C":     "Anki Browser: Cloze deletion — same number (editor)",
}

# System-level shortcuts
_SYSTEM_BLOCKED: Dict[str, str] = {}

if is_mac:
    _SYSTEM_BLOCKED.update({
        "Meta+Shift+3":     "macOS: Screenshot (full screen)",
        "Meta+Shift+4":     "macOS: Screenshot (selection)",
        "Meta+Shift+5":     "macOS: Screenshot / recording panel",
        "Meta+Ctrl+Q":      "macOS: Lock Screen",
        "Meta+Ctrl+F":      "macOS: fill screen",
    })

if is_win:
    _SYSTEM_BLOCKED.update({
        "Ctrl+Alt+Del":     "Windows: Security screen",
        "Ctrl+Shift+Esc":   "Windows: Task Manager",
    })

if not is_mac and not is_win:
    # Linux — common desktop environment defaults
    _SYSTEM_BLOCKED.update({
        "Ctrl+Alt+Del":     "Linux: Logout / shutdown dialog",
        "Ctrl+Alt+L":       "Linux: Lock screen (KDE / GNOME)",
        "Ctrl+Alt+T":       "Linux: Open terminal (GNOME / Ubuntu)",
        "Ctrl+Alt+Esc":     "Linux: Kill window / System monitor (KDE)",
    })


# Common add-on shortcuts (warning level — user can override)
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

# ---------------------------------------------------------------------------------------
# internal helpers

def _extract_first_combination(seq: QKeySequence) -> str:
    """Return the first key combination in portable text format.

    Multi-key sequences like "Ctrl+Alt+U, Ctrl+Alt+I" only have their
    first combination validated (the secondary is a fallback).
    """
    text = seq.toString(QKeySequence.SequenceFormat.PortableText)
    return text.split(",", 1)[0].strip()


def _modifier_count(combo: str) -> int:
    modifiers = {"Ctrl", "Alt", "Shift", "Meta"}
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    return sum(1 for p in parts if p in modifiers)


# ---------------------------------------------------------------------------------------
# main public function

def validate_shortcut(seq: QKeySequence, context: Context) -> ValidationResult:
    # Validate a shortcut with set rules and known (potential) collisions.
    # Empty shortcut is always valid (no shortcut configured)
    if seq.isEmpty():
        return ValidationResult(True, None, "")

    combo = _extract_first_combination(seq)

    # Must have at least 2 modifier keys (Ctrl, Alt, Shift, Meta) to be valid, imo two-button shortcuts are too simply pressed by accident and conflict with built-in shortcuts too often
    if _modifier_count(combo) < 2:
        return ValidationResult(
            False,
            Severity.BLOCKED,
            f"'{combo}' must use at least two modifier keys "
            f"(e.g. Ctrl+Alt+U). Single-modifier shortcuts are too likely "
            f"to conflict with Anki's built-in shortcuts.",
        )

    # Build the effective blacklists for this context
    blocked: Dict[str, str] = dict(_SYSTEM_BLOCKED)
    warning: Dict[str, str] = dict(_ADDON_WARNING)

    if context == Context.MAIN_WINDOW:
        blocked.update(_ANKI_MAIN_BLOCKED)
    elif context == Context.BROWSER:
        blocked.update(_ANKI_BROWSER_BLOCKED)

    if combo in blocked:
        return ValidationResult(
            False,
            Severity.BLOCKED,
            f"'{combo}' conflicts with {blocked[combo]}.\n\n"
            f"Please choose a different shortcut.",
            blocked[combo],
        )


    if combo in warning:
        return ValidationResult(
            True,  # technically valid, but needs confirmation
            Severity.WARNING,
            f"'{combo}' may conflict with {warning[combo]}.\n\n"
            f"Do you want to use it anyway?",
            warning[combo],
        )


    return ValidationResult(True, None, "")
