"""Connect to the Google Sheets API with OAuth ("sign in with Google").

How it works:
1. credentials.json (downloaded from Google Cloud) says which app is asking.
2. The first time, a browser opens, you sign in and approve access. Google
   hands back a token, which is saved so later runs don't need the browser.
3. After that, the saved token is reused. It expires about every hour, and the
   library quietly refreshes it.

There are two separate sign-ins, each with its own token file:
- read-only (token.json): used by every read tool. Can't change the sheet.
- read-write (token_write.json): used only by add_transaction, and only if you
  create it on purpose with --allow-writes. Least privilege: the read tools
  never hold write power.

The MCP server only ever uses step 3 (interactive=False). It runs inside Claude
Desktop and talks over stdin/stdout, so it must never open a browser or print.
Do the one-time sign-in with:  python -m finance_tracker.check_connection
"""

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import config

READ_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
WRITE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]  # read + write

SIGN_IN_COMMAND = "python -m finance_tracker.check_connection"


class SetupError(Exception):
    """Google setup is missing or expired. The message says how to fix it."""


def get_credentials(interactive: bool = False, write: bool = False) -> Credentials:
    """Return working Google credentials.

    write=False uses the read-only sign-in; write=True the separate read-write one.
    interactive=True may open a browser to sign in (only for check_connection).
    interactive=False never does; it raises SetupError instead.
    """
    scopes = WRITE_SCOPES if write else READ_SCOPES
    token_path = config.write_token_file() if write else config.token_file()
    sign_in = SIGN_IN_COMMAND + (" --allow-writes" if write else "")

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(creds, token_path)
            return creds
        except RefreshError:
            creds = None  # e.g. the 7-day limit for apps in Google's "Testing" mode

    if not interactive:
        raise SetupError(f"Not signed in to Google (or the sign-in expired). Run: {sign_in}")

    secret_path = config.client_secret_file()
    if not secret_path.exists():
        raise SetupError(
            f"Google OAuth client file not found: {secret_path}\n"
            "Download it from Google Cloud (see docs/google-setup.md) and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), scopes)
    creds = flow.run_local_server(port=0)  # opens the browser; port=0 = any free port
    save_token(creds, token_path)
    return creds


def save_token(creds: Credentials, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")


def sheets_service(interactive: bool = False, write: bool = False):
    """A ready-to-use Google Sheets API client (read-only unless write=True)."""
    return build("sheets", "v4", credentials=get_credentials(interactive, write), cache_discovery=False)
