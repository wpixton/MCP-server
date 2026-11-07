"""Connect to the Google Sheets API with OAuth ("sign in with Google").

How it works:
1. credentials.json (downloaded from Google Cloud) says which app is asking.
2. The first time, a browser opens, you sign in and approve access. Google
   hands back a token, which is saved to token.json.
3. After that, the saved token is reused. It expires about every hour, and the
   library quietly refreshes it.

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

# Least privilege: read-only for now. Writing (add_transaction) gets its own,
# explicitly enabled permission in a later milestone.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SIGN_IN_COMMAND = "python -m finance_tracker.check_connection"


class SetupError(Exception):
    """Google setup is missing or expired. The message says how to fix it."""


def get_credentials(interactive: bool = False) -> Credentials:
    """Return working Google credentials.

    interactive=True may open a browser to sign in (only for check_connection).
    interactive=False never does; it raises SetupError instead.
    """
    token_path = config.token_file()

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(creds)
            return creds
        except RefreshError:
            creds = None  # e.g. the 7-day limit for apps in Google's "Testing" mode

    if not interactive:
        raise SetupError(f"Not signed in to Google (or the sign-in expired). Run: {SIGN_IN_COMMAND}")

    secret_path = config.client_secret_file()
    if not secret_path.exists():
        raise SetupError(
            f"Google OAuth client file not found: {secret_path}\n"
            "Download it from Google Cloud (see docs/google-setup.md) and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    creds = flow.run_local_server(port=0)  # opens the browser; port=0 = any free port
    save_token(creds)
    return creds


def save_token(creds: Credentials) -> None:
    path = config.token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")


def sheets_service(interactive: bool = False):
    """A ready-to-use Google Sheets API client."""
    return build("sheets", "v4", credentials=get_credentials(interactive), cache_discovery=False)
