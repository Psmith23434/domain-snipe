# config.py
# Credentials are loaded from a local .env file that is never committed to git.
# See config.example.env for the required variable names.
#
# First-time setup:
#   1. Copy config.example.env  →  .env  (in this folder)
#   2. Fill in your values in .env
#   3. pip install python-dotenv   (once)
#
# Get your API key/secret at: https://www.spaceship.com/account/api-management/
# Get your Contact ID from:   Spaceship dashboard → Contacts

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Load .env from the same directory as this file, regardless of cwd
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)
except ImportError:
    # python-dotenv not installed — fall back to raw os.environ only
    pass

def _require(name: str) -> str:
    """Read an env var; raise a clear error if it is missing or still a placeholder."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(
            f"\n\n[domain-snipe] Missing credential: {name}\n"
            f"  → Create a .env file in the project folder and add:\n"
            f"       {name}=your_value_here\n"
            f"  → See config.example.env for a template.\n"
        )
    return value


API_KEY    = _require("SPACESHIP_API_KEY")
API_SECRET = _require("SPACESHIP_API_SECRET")
CONTACT_ID = _require("SPACESHIP_CONTACT_ID")
BASE_URL   = os.environ.get("SPACESHIP_BASE_URL", "https://spaceship.dev/api/v1")
