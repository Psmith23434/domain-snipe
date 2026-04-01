# persistence.py
import json
import os
import tempfile
from pathlib import Path

from utils import normalize_domain

_DIR = Path(__file__).parent

WATCHLIST_FILE    = _DIR / "watchlist.json"
SETTINGS_FILE     = _DIR / "settings.json"
RAMPAGE_QUEUE_FILE = _DIR / "rampage_queue.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, data) -> None:
    """
    Serialise *data* to JSON and write it atomically.

    Writes to a sibling temp file first, then calls os.replace() which is
    guaranteed atomic on all POSIX systems and on Windows (Python 3.3+).
    This means a crash or power-loss mid-write can never corrupt the file —
    the old version stays intact until the new one is fully flushed to disk.
    """
    path = Path(path)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())   # ensure bytes reach the OS buffer
        os.replace(tmp_path, path)
    except Exception:
        # Clean up the orphaned temp file if anything goes wrong
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _load_json(path: Path, fallback):
    """Load JSON from *path*, returning *fallback* on any read/parse error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback
    except Exception:
        return fallback


def _clean_domains(raw) -> list:
    """Normalise and deduplicate a raw domain list."""
    if not isinstance(raw, list):
        return []
    seen = set()
    out  = []
    for item in raw:
        d = normalize_domain(item)
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

def load_watchlist() -> list:
    return _clean_domains(_load_json(WATCHLIST_FILE, []))


def save_watchlist(domains) -> None:
    _atomic_write(WATCHLIST_FILE, _clean_domains(domains))


# ---------------------------------------------------------------------------
# Rampage queue  (own file — kept separate from user preferences)
# ---------------------------------------------------------------------------

def load_rampage_queue() -> list:
    return _clean_domains(_load_json(RAMPAGE_QUEUE_FILE, []))


def save_rampage_queue(domains) -> None:
    _atomic_write(RAMPAGE_QUEUE_FILE, _clean_domains(domains))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

_SETTINGS_DEFAULTS = {
    "always_on_top":    False,
    "minimize_to_tray": True,
    "max_premium":      500,
    "sound":            True,
}

def load_settings() -> dict:
    defaults = dict(_SETTINGS_DEFAULTS)
    data = _load_json(SETTINGS_FILE, {})
    if isinstance(data, dict):
        # Strip legacy rampage_queue key if it snuck in from an old settings file
        data.pop("rampage_queue", None)
        defaults.update(data)
    return defaults


def save_settings(settings: dict) -> None:
    clean = {k: v for k, v in settings.items() if k != "rampage_queue"}
    _atomic_write(SETTINGS_FILE, clean)
