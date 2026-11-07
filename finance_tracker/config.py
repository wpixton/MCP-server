"""Settings for the finance tracker server. Everything comes from environment variables.

FINANCE_SHEET_ID         The real Google Sheet to read (the ID or the full link).
                         If this is NOT set, the server uses the fake sample tracker,
                         so nothing touches real data unless you ask for it.
FINANCE_SAMPLE_PATH      Optional: use a different fake .xlsx (the tests do this).
FINANCE_CREDENTIALS_DIR  Optional: where the Google sign-in files live.
                         Default: a folder in your home directory, outside the repo,
                         so they can never be committed by accident.
FINANCE_ALLOW_REAL_WRITES  Must be "yes" before add_transaction may write to the
                         real Google Sheet. Anything else (or unset) = refuse.
                         Writes to the fake sample are always allowed.
"""

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLE_PATH = PROJECT_ROOT / "sample_data" / "sample_finance_tracker.xlsx"
DEFAULT_CREDENTIALS_DIR = Path.home() / ".finance-tracker-mcp"

SHEET_ID_VAR = "FINANCE_SHEET_ID"
SAMPLE_PATH_VAR = "FINANCE_SAMPLE_PATH"
CREDENTIALS_DIR_VAR = "FINANCE_CREDENTIALS_DIR"
ALLOW_WRITES_VAR = "FINANCE_ALLOW_REAL_WRITES"


def _read_env(name: str) -> str | None:
    """An environment variable's value, or None if it's unset or blank."""
    value = os.environ.get(name, "").strip().strip('"')  # tolerate a quoted Windows path
    return value or None


def sheet_id() -> str | None:
    """The Google Sheet ID to use, or None to use the fake sample.

    Accepts either the bare ID or the whole link you copy from the browser:
    https://docs.google.com/spreadsheets/d/<ID>/edit...
    """
    value = _read_env(SHEET_ID_VAR)
    if value is None:
        return None
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value)
    return match.group(1) if match else value


def using_real_sheet() -> bool:
    return sheet_id() is not None


def sample_path() -> Path:
    value = _read_env(SAMPLE_PATH_VAR)
    return Path(value).expanduser() if value else DEFAULT_SAMPLE_PATH


def credentials_dir() -> Path:
    value = _read_env(CREDENTIALS_DIR_VAR)
    return Path(value).expanduser() if value else DEFAULT_CREDENTIALS_DIR


def client_secret_file() -> Path:
    """The OAuth client file you download from Google Cloud (identifies this app)."""
    return credentials_dir() / "credentials.json"


def token_file() -> Path:
    """Saved after you sign in once, so later runs don't need the browser. Read-only."""
    return credentials_dir() / "token.json"


def write_token_file() -> Path:
    """A separate sign-in that may edit the sheet. Only created if you ask for it."""
    return credentials_dir() / "token_write.json"


def real_writes_allowed() -> bool:
    """True only when FINANCE_ALLOW_REAL_WRITES is explicitly yes/true/1."""
    return (_read_env(ALLOW_WRITES_VAR) or "").lower() in ("yes", "true", "1")
