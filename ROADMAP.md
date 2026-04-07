# Roadmap

This file tracks open bugs, known issues, and planned improvements for **domain-snipe**.
All items from the initial code audit are listed below. Status is updated as work progresses.

---

## Overview

| ID | Title | File(s) | Priority | Status |
|---|---|---|---|---|
| BUG-01 | API credentials stored in source code | `config.py` | 🔴 Critical | ✅ Resolved |
| BUG-02 | No atomic writes — watchlist data loss on crash | `persistence.py` | 🔴 Critical | ✅ Resolved |
| BUG-03 | Table row index map corrupts on row deletion | `mixin_tables.py` | 🔴 Critical | ✅ Resolved |
| BUG-04 | GUI widget mutations from background threads | `mixin_monitor.py`, `mixin_tables.py`, `mixin_actions.py` | 🟠 High | ✅ Resolved |
| BUG-05 | Shared dict mutation without lock (data race) | `mixin_actions.py`, `mixin_monitor.py` | 🟠 High | ✅ Resolved |
| MISSING-01 | No `requirements.txt` / `pyproject.toml` | project root | 🟠 High | ❌ Open |
| BUG-06 | Hardcoded TLD prices go stale | `constants.py` | 🟡 Medium | ❌ Open |
| BUG-07 | String-matching status dispatch is fragile | `mixin_handlers.py`, `sniper.py` | 🟡 Medium | ❌ Open |
| IMPROVEMENT-01 | `mixin_builders.py` has no sub-structure (41 KB) | `mixin_builders.py` | 🟡 Medium | ❌ Open |
| IMPROVEMENT-02 | No theme system — inline scattered stylesheets | `mixin_builders.py` | 🟡 Medium | ❌ Open |
| IMPROVEMENT-03 | Watchlist saved to `~` instead of OS app data dir | `persistence.py` | 🟡 Medium | ❌ Open |
| IMPROVEMENT-04 | `format_countdown` returns negative values | `utils.py` | 🟡 Medium | ❌ Open |
| IMPROVEMENT-05 | No confirmation before clearing Rampage queue | `mixin_actions.py` | 🟡 Medium | ❌ Open |
| IMPROVEMENT-06 | No unit tests | `utils.py`, `api.py`, `sniper.py` | 🟢 Low | ❌ Open |
| IMPROVEMENT-07 | Column index constants are fragile integers | `constants.py` | 🟢 Low | ❌ Open |
| IMPROVEMENT-08 | README was empty | `README.md` | 🟢 Low | ✅ Resolved |

**Progress: 6 / 16 resolved**

---

## 🔴 Critical — All Resolved

### [BUG-01] API credentials stored in source code
**File:** `config.py`
**Status:** ✅ Resolved — 2026-04-07

API keys, secrets, and the Contact ID were hardcoded as plain strings. If `config.py` was ever committed with real values, credentials would be permanently exposed in git history.

**Resolution:** `config.py` now loads credentials from a local `.env` file via `python-dotenv`. `config.py` and `.env` are both listed in `.gitignore`. A `config.example.env` template is shipped in the repo. The app raises a clear `EnvironmentError` at startup if any required variable is missing.

---

### [BUG-02] No atomic writes — watchlist data loss on crash
**File:** `persistence.py`
**Status:** ✅ Resolved — 2026-04-07 (verified 2026-04-07)

`open(path, "w")` truncated the file before writing began. A crash mid-write would produce a zero-byte JSON file.

**Resolution:** `persistence.py` already contained `_atomic_write()` using `tempfile.mkstemp`, `os.fsync`, and `os.replace`. Verified present in the current codebase. No further changes needed.

---

### [BUG-03] Table row index map corrupts on row deletion
**File:** `mixin_tables.py`
**Status:** ✅ Resolved — 2026-04-07 (verified 2026-04-07)

Stored integer Qt row indices would become stale after row deletion.

**Resolution:** `mixin_tables.py` already contained `_rebuild_rows()` which re-scans the live Qt table after every deletion or reorder and rebuilds the rowmap from scratch. Verified present in the current codebase. No further changes needed.

---

## 🟠 High Priority

### [BUG-04] GUI widget mutations from background threads (Qt thread-safety)
**Files:** `mixin_monitor.py`, `mixin_tables.py`, `mixin_actions.py`
**Status:** ✅ Resolved — 2026-04-07 (verified 2026-04-07)

Several code paths risked calling widget-touching methods from non-main threads.

**Resolution:** Verified that all background-thread callbacks in `mixin_monitor.py` exclusively use `self.signals.*.emit()`. No direct widget access occurs from scheduler or worker threads. Qt thread-safety contract is met.

---

### [BUG-05] Shared dict mutation without lock (data race)
**Files:** `mixin_actions.py`, `mixin_monitor.py`
**Status:** ✅ Resolved — 2026-04-07

Three call sites in `mixin_actions.py` read or mutated `monitor_rows` / `rampage_rows` from the GUI thread without holding `monitor_scheduler_lock`, creating TOCTOU data races with the background scheduler thread:

1. `add_domain()` — passed `self.monitor_rows.keys()` to `save_watchlist()` without a lock
2. `_bulk_add_monitor()` — same
3. `clear_rampage_queue()` — called `self.rampage_rows.clear()` with no lock while the Rampage worker thread could be iterating the dict

**Resolution:**
- `add_domain()` and `_bulk_add_monitor()`: snapshot `monitor_rows.keys()` inside `with self.monitor_scheduler_lock:` before passing to `save_watchlist()`.
- `clear_rampage_queue()`: snapshot and clear `rampage_rows` inside `with self.monitor_scheduler_lock:`; `stop_domain()` calls moved outside the lock to avoid holding it during signal emissions.
- `remove_monitor()`: also updated to snapshot keys under lock before `save_watchlist()`.

---

### [MISSING-01] No `requirements.txt` / `pyproject.toml`
**File:** project root
**Status:** ❌ Open

The project has no declared Python dependencies. New users must guess what to install.

**Fix:** Add a `requirements.txt`:
```
PyQt5>=5.15
requests>=2.31
python-dotenv>=1.0
platformdirs>=4.0
```

---

## 🟡 Medium Priority — Open

### [BUG-06] Hardcoded TLD prices go stale
**File:** `constants.py`
**Status:** ❌ Open

`TLD_PRICES` contains prices that were correct at time of writing but will drift as Spaceship updates its pricing. The app currently shows wrong prices silently.

**Fix:** Fetch live pricing from the Spaceship API (`/v1/domains/{tld}/pricing`) at startup and cache it. Keep the hardcoded dict as a fallback only.

---

### [BUG-07] String-matching status dispatch is fragile
**File:** `mixin_handlers.py`
**Status:** ❌ Open

`_handle_status_update` uses `if "available" in status` substring matching to branch behaviour. Any API message wording change silently breaks the dispatch. Same applies to `PERMANENT_ERRORS` in `sniper.py`.

**Fix:** Use structured status codes or a dedicated enum rather than substring matching. Parse API error codes directly instead of scanning message strings.

---

### [IMPROVEMENT-01] `mixin_builders.py` has no sub-structure (41 KB)
**File:** `mixin_builders.py`
**Status:** ❌ Open

At 41 KB, this is the largest file and a maintainability bottleneck. All tab UIs, table construction, settings panel, and tray icon live in one monolithic mixin. A change to the Rampage tab requires navigating thousands of lines.

**Fix:** Split into `builder_monitor.py`, `builder_rampage.py`, `builder_settings.py`, `builder_log.py`. Move each tab's construction into its own builder mixin.

---

### [IMPROVEMENT-02] No theme system — inline scattered stylesheets
**File:** `mixin_builders.py`
**Status:** ❌ Open

Colors and fonts are set as inline `setStyleSheet()` strings scattered across the builder. A single colour change requires hunting dozens of lines. There is no light mode.

**Fix:** Define a single `theme.py` module with colour constants and a `apply_theme(widget)` helper. Build a Qt stylesheet string from those constants and apply it once at startup via `QApplication.setStyleSheet()`.

---

### [IMPROVEMENT-03] Watchlist saved to `~` instead of OS app data directory
**File:** `persistence.py`
**Status:** ❌ Open

JSON files are saved to the user's home directory root, which is non-standard on all platforms.

**Fix:** Use the `platformdirs` library: `user_data_dir("domain-snipe", "Psmith23434")` returns the correct path on Windows (`%APPDATA%`), macOS (`~/Library/Application Support`), and Linux (`~/.local/share`).

---

### [IMPROVEMENT-04] `format_countdown` returns negative values
**File:** `utils.py`
**Status:** ❌ Open

When `t < 0` (the scheduled check time is in the past), the function returns a negative countdown string instead of `"Now"` or `"Overdue"`.

**Fix:** Add `if seconds <= 0: return "Now"` at the top of the function.

---

### [IMPROVEMENT-05] No confirmation before clearing Rampage queue
**File:** `mixin_actions.py`
**Status:** ❌ Open

`clear_rampage_queue()` immediately wipes the entire queue with no `QMessageBox.question()` confirmation. One misclick destroys the queue.

**Fix:** Add a confirmation dialog: *"Clear all X domains from the Rampage queue? This cannot be undone."*

---

## 🟢 Low Priority — Open

### [IMPROVEMENT-06] No unit tests
**File:** `utils.py`, `api.py`, `sniper.py`
**Status:** ❌ Open

Pure utility functions (`normalize_domain`, `format_price`, `_sleep_with_stop`, etc.) have zero test coverage.

**Fix:** Add a `tests/` directory with `pytest` tests for all pure functions. Mock the HTTP layer to test `api.py` without live API calls.

---

### [IMPROVEMENT-07] Column index constants are fragile integers
**File:** `constants.py`
**Status:** ❌ Open

`COL_DRAG = 0`, `COL_DOMAIN = 3`, etc. are manual integer assignments. Inserting a column requires updating every constant by hand.

**Fix:** Use an `IntEnum` with `auto()` so column order is maintained automatically:
```python
from enum import IntEnum, auto
class Col(IntEnum):
    DRAG    = 0
    SNIPE   = auto()
    AUTOBUY = auto()
    DOMAIN  = auto()
    ...
```

---

## Completed

| ID | Description | Resolved |
|---|---|---|
| BUG-01 | API credentials stored in source code | 2026-04-07 |
| BUG-02 | No atomic writes — watchlist data loss on crash | 2026-04-07 (verified) |
| BUG-03 | Table row index map corrupts on row deletion | 2026-04-07 (verified) |
| BUG-04 | GUI widget mutations from background threads | 2026-04-07 (verified) |
| BUG-05 | Shared dict mutation without lock (data race) | 2026-04-07 |
| IMPROVEMENT-08 | Write README | 2026-04-07 |

---

*Last updated: 2026-04-07*
