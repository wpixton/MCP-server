"""Tests for the Google sign-in logic. None of these touch the network."""

import json

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from finance_tracker import check_connection, config, google_sheets


def write_fake_token(expiry: str) -> None:
    """Save a made-up token.json, shaped like the real one."""
    path = config.token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "token": "fake-access-token",
        "refresh_token": "fake-refresh-token",
        "client_id": "fake-client.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": google_sheets.READ_SCOPES,
        "expiry": expiry,
    }))


def test_server_mode_never_opens_a_browser_when_not_signed_in():
    with pytest.raises(google_sheets.SetupError, match="check_connection"):
        google_sheets.get_credentials(interactive=False)


def test_sign_in_explains_missing_client_file():
    with pytest.raises(google_sheets.SetupError, match="credentials.json"):
        google_sheets.get_credentials(interactive=True)


def test_saved_token_is_reused():
    write_fake_token(expiry="2099-01-01T00:00:00Z")
    creds = google_sheets.get_credentials(interactive=False)
    assert creds.token == "fake-access-token"


def test_expired_sign_in_gives_a_clear_error(monkeypatch):
    # Simulates Google rejecting the refresh, e.g. the 7-day limit in "Testing" mode.
    write_fake_token(expiry="2000-01-01T00:00:00Z")

    def refuse(self, request):
        raise RefreshError("invalid_grant")

    monkeypatch.setattr(Credentials, "refresh", refuse)
    with pytest.raises(google_sheets.SetupError, match="expired"):
        google_sheets.get_credentials(interactive=False)


def test_permission_is_read_only():
    assert google_sheets.READ_SCOPES == ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def test_read_only_sign_in_never_grants_writing():
    # Signed in read-only, asking for write access must still fail -- it needs its own sign-in.
    write_fake_token(expiry="2099-01-01T00:00:00Z")
    with pytest.raises(google_sheets.SetupError, match="--allow-writes"):
        google_sheets.get_credentials(interactive=False, write=True)


def test_write_sign_in_uses_its_own_token_file():
    assert config.write_token_file() != config.token_file()
    assert config.write_token_file().parent == config.token_file().parent


def test_check_connection_requires_a_sheet_id(capsys):
    assert check_connection.main([]) == 1
    assert config.SHEET_ID_VAR in capsys.readouterr().out


def test_check_connection_asks_only_for_structure():
    # Cell values live under "sheets.data". The field mask must never request it.
    assert "data" not in check_connection.STRUCTURE_ONLY
