# Roadmap

This file tracks open bugs, known issues, and planned improvements for **domain-snipe**.
All items from the initial code audit are listed below. Status is updated as work progresses.

---

## Overview

| ID | Title | File(s) | Priority | Status |
|---|---|---|---|---|
| BUG-01 | API credentials stored in source code | `config.py` | 🔴 Critical | ✅ Resolved |
| BUG-02 | No atomic writes — watchlist data loss on crash | `persistence.py` | 🔴 Critical | ❌ Open |
| BUG-03 | Table row index map corrupts on row deletion | `mixin_tables.py` | 🔴 Critical | ❌ Open |
| BUG-04 | GUI widget mutations from background threads | `mixin_monitor.py`, `mixin_tables.py`, `mixin_actions.py` | 🟠 High | ❌ Open |
| BUG-05 | Shared dict mutation without lock (data race) | `mixin_actions.py`, `mixin_monitor.py` | 🟠 High | ❌ Open |
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

**Progress: 2 / 16 resolved**

---

## 🔴 Critical

### [BUG-01] API credentials stored in source code
**File:** `config.py`
**Status:** ✅ Resolved — 2026-04-07

API keys, secrets, and the Contact ID were hardcoded as plain strings. If `config.py` was ever committed with real values, credentials would be permanently exposed in git history.

**Resolution:** `config.py` now loads credentials from a local `.env` file via `python-dotenv`. `config.py` and `.env` are both listed in `.gitignore`. A `config.example.env` template is shipped in the repo. The app raises a clear `EnvironmentError` at startup if any required variable is missing.

---

### [BUG-02] No atomic writes — watchlist data loss on crash
**File:** `persistence.py`
**Status:** ❌ Open

`open(path, "w")` truncates the file before writing begins. A crash, power loss, or OS kill mid-write produces a zero-byte or corrupt JSON file, permanently destroying the watchlist and Rampage queue.

**Fix:** Write to a `.tmp` sibling file and use `os.replace()` to atomically swap it in. Also add schema versioning so future format changes don't silently corrupt old files.

---

### [BUG-03] Table row index map corrupts on row deletion
**File:** `mixin_tables.py`
**Status:** ❌ Open

`self.monitor_rows` and `self.rampage_rows` store integer Qt row indices. When any row above a domain is removed, Qt shifts every lower row up by one — the stored indices become wrong. This causes wrong rows to receive status updates, wrong rows to be acted upon, and potential silent data mixing.

**Fix:** Switch to a model-based approach (`QAbstractTableModel`) where rows are identified by domain key, not by integer index. Alternatively, store a sentinel `QTableWidgetItem` per row and call `indexFromItem()` at access time.

---

## 🟠 High Priority — Open

### [BUG-04] GUI widget mutations from background threads (Qt thread-safety)
**Files:** `mixin_monitor.py`, `mixin_tables.py`, `mixin_actions.py`
**Status:** ❌ Open

Several code paths call widget-touching methods (e.g., `launch_rampage()`, `_checked_in_table()`) from non-main threads. Qt requires all widget access to happen on the main thread. Violations cause random crashes and undefined rendering behaviour that are extremely hard to reproduce.

**Fix:** Ensure all widget mutations go through Qt signals. Audit every background thread callback and replace direct widget calls with `signals.emit()` calls.

---

### [BUG-05] Shared dict mutation without lock (data race)
**Files:** `mixin_actions.py`, `mixin_monitor.py`
**Status:** ❌ Open

`self.monitor_scheduler_state` and `self.monitor_rows` are written from both the GUI thread and the monitor scheduler background thread without consistently holding `self.monitor_scheduler_lock`. This is a classic TOCTOU data race that can produce corrupted state under load.

**Fix:** Enforce a strict locking discipline — every read and write of the shared state dicts must happen inside `with self.monitor_scheduler_lock:`.

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
| IMPROVEMENT-08 | Write README | 2026-04-07 |

---

*Last updated: 2026-04-07*
