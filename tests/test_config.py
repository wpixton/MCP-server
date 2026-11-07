"""Tests for config.py: every setting comes from an environment variable."""

from pathlib import Path

from finance_tracker import config

SHEET_ID = "1AbC_def-123"


def test_fake_sample_is_the_default():
    assert config.sheet_id() is None
    assert config.using_real_sheet() is False
    assert config.sample_path() == config.DEFAULT_SAMPLE_PATH


def test_sheet_id_from_bare_id(monkeypatch):
    monkeypatch.setenv(config.SHEET_ID_VAR, SHEET_ID)
    assert config.sheet_id() == SHEET_ID
    assert config.using_real_sheet() is True


def test_sheet_id_from_full_link(monkeypatch):
    link = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?usp=sharing"
    monkeypatch.setenv(config.SHEET_ID_VAR, link)
    assert config.sheet_id() == SHEET_ID


def test_blank_sheet_id_means_sample(monkeypatch):
    monkeypatch.setenv(config.SHEET_ID_VAR, "   ")
    assert config.using_real_sheet() is False


def test_sample_path_override_strips_quotes(monkeypatch):
    monkeypatch.setenv(config.SAMPLE_PATH_VAR, r'"C:\Demo\fake tracker.xlsx"')
    assert config.sample_path() == Path(r"C:\Demo\fake tracker.xlsx")


def test_credential_files_live_in_credentials_dir(monkeypatch, tmp_path):
    monkeypatch.setenv(config.CREDENTIALS_DIR_VAR, str(tmp_path))
    assert config.client_secret_file() == tmp_path / "credentials.json"
    assert config.token_file() == tmp_path / "token.json"


def test_default_credentials_dir_is_outside_the_repo():
    # Secrets default to the home folder, so git never even sees them.
    assert not config.DEFAULT_CREDENTIALS_DIR.is_relative_to(config.PROJECT_ROOT)
