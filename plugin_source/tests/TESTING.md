# AnkiCollab Test Suite

## Quick Start

```bash
# From the addon root (1957538407/)
python -m pytest tests/            # run all 185 tests
python -m pytest tests/ -x         # stop on first failure
python -m pytest tests/ -k utils   # run only tests matching "utils"
```

Requires: `pytest`, `pytest-asyncio`, `requests-mock`, `factory-boy` (all in `.venv/`).

---

## Architecture Overview

### The Problem

The addon runs inside Anki, which provides `aqt.mw` (the main window singleton)
and `anki.*` packages. Every addon module does `from aqt import mw` at import
time, creating a module-level binding. Outside Anki, none of these packages
exist.

Additionally, the addon's `__init__.py` does `from .main import *`, which
triggers heavy side effects (UI hooks, menu registrations, etc.) that crash
without a running Anki instance. All modules use **relative imports**
(`from .var_defs import ...`), so they must be loaded as submodules of the
numeric package `1957538407`.

### The Solution: Two-Layer Bootstrap

#### Layer 1: Root `conftest.py` (addon root)

Runs before pytest collects any test files. It:

1. **Sets `SKIP_INIT=1`** in the environment
2. **Installs fake modules** (`aqt`, `aqt.qt`, `anki.*`, `sentry_sdk`, etc.)
   as `MagicMock` objects in `sys.modules`.
3. **Registers the addon as a package** — creates a dummy `types.ModuleType`
   for `1957538407` in `sys.modules`, preventing pytest from importing the
   real `__init__.py` (which would run `from .main import *`).
4. **Pre-registers `main` as a MagicMock** — `main.py` has circular deps
   and side effects; other modules that `from . import main` get the mock.
5. **Imports all addon submodules in dependency order** via
   `importlib.import_module(".module_name", package="1957538407")`,
   registering each under both `1957538407.module_name` and `module_name`
   in `sys.modules`. If any module fails to import, a MagicMock fallback
   is registered so downstream modules don't cascade-fail.

Key detail: `sys.modules["__init__"] = _pkg` prevents pytest's
`--import-mode=importlib` from re-importing the real `__init__.py` during
package collection.

#### Layer 2: Unit `tests/unit/conftest.py`

Provides the autouse `mw_mock` fixture that runs before every test:

1. Builds a fresh `MagicMock` via `create_mock_mw(config=sample_config)`.
2. **Patches `aqt.mw`** so any code doing `import aqt; aqt.mw` sees the mock.
3. **Patches the module-level `mw`** in every addon module that imported it
   at load time (`utils.mw`, `auth_manager.mw`, `stats.mw`, etc.).
   This is critical: `from aqt import mw` binds `mw` at import time,
   so patching only `aqt.mw` does NOT update the already-bound reference.

---

## File Layout

```
1957538407/
├── conftest.py                 # Root bootstrap (fake modules, package registration)
├── pytest.ini                  # Test configuration
├── tests/
│   ├── __init__.py             # Empty (marks tests as package)
│   ├── conftest.py             # Shared fixtures (tmp_media_dir, sample_config)
│   ├── mocks.py                # create_mock_mw(), FakeNote, FakeCard, FakeCol
│   ├── factories.py            # factory_boy factories for test data
│   ├── TESTING.md              # This file
│   └── unit/
│       ├── __init__.py
│       ├── conftest.py         # Autouse mw_mock fixture (patches all modules)
│       ├── test_auth_manager.py
│       ├── test_export_manager.py
│       ├── test_identifier.py
│       ├── test_import_manager.py
│       ├── test_media_manager.py
│       ├── test_stats.py
│       ├── test_thread.py
│       ├── test_utils.py
│       └── test_var_defs.py
```

---

## What Each Test File Covers

### `test_var_defs.py` (9 tests)
Constants and configuration: `API_BASE_URL`, `VERSION`, `DEFAULT_PROTECTED_TAGS`,
tag/field prefixes, Sentry config. These break immediately if you rename or
remove a constant.

### `test_utils.py` (~35 tests)
Core utility layer — the most critical file:
- **Collection guards**: `ensure_collection()`, `is_collection_available()`,
  `check_collection_or_abort()` — tests both success and `mw.col=None` paths.
- **DeckManager**: Filtering reserved keys (`settings`, `auth`), hash lookup,
  iteration, context-manager save, None config resilience.
- **Lookup chain**: `get_timestamp()` → `get_hash_from_local_id()` →
  `get_did_from_hash()` → `get_local_deck_from_hash()` → `get_deck_hash_from_did()`
  with parent fallback → `get_deck_hash_from_card()` with odid + dynamic deck.
- **`get_deck_and_subdecks()`**: Recursive child traversal, invalid ID guards.
- **Backup**: Input validation (`bg+critical`), no-collection paths.

### `test_auth_manager.py` (26 tests)
Full authentication lifecycle:
- Init with empty/existing config, token storage with numeric/ISO/bad expiry.
- Token refresh flow — success, HTTP failure, network exception, missing refresh token.
- **Auto-refresh on `get_token()`** — verifies transparent refresh when near expiry.
- `is_logged_in()`, auto-approve get/set, `logout()` (server + local cleanup).

### `test_export_manager.py` (22 tests)
Media reference extraction — tests real compiled regex objects:
- Sound patterns `[sound:file.mp3]`, HTML `<img src>`, `<audio src>`,
  `<object data>`, case insensitivity, multiple matches per field.
- `_is_valid_media_file()` with real filesystem (100-byte threshold, missing, None).
- `_filter_valid_filename_mapping()` with real files on disk.
- `_handle_operation_aborted()` — distinguishes OperationAbortedError from others.

### `test_identifier.py` (9 tests)
User hash + subscription API calls (requests are mocked, logic is real):
- `get_user_hash()`: token available → success, no token → None, exception → None.
- `subscribe/unsubscribe_to_deck()`: success, no user hash, server error.

### `test_import_manager.py` (23 tests)
Deck import pipeline:
- `_fetch_manifest()`: real error handling (network, invalid JSON).
- `_safe_destination()`: path traversal attack prevention, normal resolution.
- `_coerce_subscription_payload()`: dict/list/string/no-deck-key validation.
- `_extract_media_entries()`: real zip extraction to temp dir, skip-existing,
  path prefix filtering, no-collection guard.
- **Optional tags**: lookup, change detection.
- **Note ID lookups**: batch `get_noteids_from_uuids()` / `get_guids_from_noteids()`.
- `wants_to_share_stats()`, `do_nothing()`.

### `test_stats.py` (11 tests)
Review history and analytics:
- `ReviewHistory` construction (chains `get_did_from_hash` + `get_deck_and_subdecks`).
- `calc_retention()`: boundary cases (0/0, None/None, all passed, all failed).
- `get_card_data()`: groups by deck + guid, aggregates retention/lapses/reps.
- `upload_review_history()`: compression pipeline (gzip→b64→POST), skip on no hash.
- `update_stats_timestamp()`: DeckManager context-manager mutation.

### `test_media_manager.py` (25 tests)
Media upload/download infrastructure:
- Exception class hierarchy verification.
- Constants validation (MAX_FILE_SIZE, extensions, content type map coverage).
- `RateLimiter`: token bucket — init validation, consumption, multi-request drain.
- `retry` decorator: first-try success, retry-then-recover, exhaust retries,
  no-retry on 404/401/executor_unavailable (status code inspection).
- `MediaManager` init: validation, trailing slash stripping, invalid folder.
- Helpers: `_file_exists_with_size`, `_is_anki_available` (with/without collection),
  `_ensure_executor_available` (shutdown → RuntimeError vs recreation).

### `test_thread.py` (10 tests)
Thread helpers:
- `run_function_in_thread()`: execution, arg passing, daemon flag, exception resilience.
- `run_async_function_in_thread()`: async execution with own event loop.
- `sync_run_async()`: result forwarding, exception propagation.

---

## The `mw_mock` Fixture

The `mw_mock` fixture (autouse in unit tests) provides:

| Attribute | Behavior |
|---|---|
| `mw.col` | `FakeCol` with mocked `.decks`, `.db`, `.models`, `.media`, etc. |
| `mw.addonManager.getConfig(id)` | Returns a mutable dict (shared `_config_store`) |
| `mw.addonManager.writeConfig(id, cfg)` | Updates the same `_config_store` |
| `mw.taskman.run_on_main(fn)` | Calls `fn()` synchronously |
| `mw.progress.want_cancel()` | Returns `False` |

Tests that need custom config use `mw_mock.addonManager.getConfig.side_effect`
to override the default. Tests that need `mw.col = None` use the `mw_no_col` fixture.

---

## How Tests Will Catch Real Bugs

Every test calls the **actual business function** with controlled inputs and
checks output/behavior. The mock layer only replaces Anki's runtime
(`aqt.mw`, `mw.col.db`, network calls). If you change any of these:

- **DeckManager iteration logic** → `test_filters_settings_and_auth` fails
- **Timestamp parsing format** → `test_get_timestamp_returns_float` fails
- **Deck hash lookup chain** → `test_direct_match`, `test_falls_back_to_parent` fail
- **Filtered deck detection** → `test_dynamic_deck_returns_filtered_error` fails
- **Token refresh threshold** → `test_near_expiry_returns_true` fails
- **Media regex patterns** → `test_sound_regex_simple`, `test_img_src_*` fail
- **Path traversal guard** → `test_traversal_raises` fails
- **Media extraction skip logic** → `test_skips_existing_files` fails
- **Retention calculation** → `test_all_passed`, `test_all_failed` fail
- **Retry no-retry conditions** → `test_no_retry_on_404`, `test_no_retry_on_401` fail

---

## Adding New Tests

1. Import from the **short module name** (e.g., `from utils import DeckManager`).
2. Use `mw_mock` fixture for anything touching `mw`. Override config via
   `mw_mock.addonManager.getConfig.side_effect = lambda *a, **kw: dict(my_config)`.
3. Mock network calls with `@patch("module_name.requests.post")`.
4. For new modules that use `from aqt import mw`, add the module name to
   `_MW_MODULES` in `tests/unit/conftest.py`.
5. For new addon submodules, add them to `_ADDON_MODULES_ORDERED` in the
   root `conftest.py` (respect dependency order).

---

## Known Limitations

- **No UI tests**: Dialogs, menus, and Qt widgets are fully mocked. Testing
  those requires `pytest-anki` with a real Anki instance.
- **`main.py` is a MagicMock**: The main module triggers too many side effects.
  Functions it exports can't be unit tested this way.
- **`.oga` content type gap**: `.oga` is in `ALLOWED_EXTENSIONS` but missing
  from `CONTENT_TYPE_MAP` — documented in test, not a test bug.
- **`calc_retention` truncation**: `int(passed / total) * 100` truncates to 0
  for anything below 100%. Tests are written to match this actual behavior.
