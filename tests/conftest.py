"""Shared test setup. pytest loads this file automatically."""

import pytest

from finance_tracker import config


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    """Runs before every test.

    Clears the finance environment variables so settings on this machine (like a
    real FINANCE_SHEET_ID) can't leak into a test, and points the credentials
    folder at an empty temp directory so no test can touch a real Google sign-in.
    """
    for name in (config.SHEET_ID_VAR, config.SAMPLE_PATH_VAR, config.CREDENTIALS_DIR_VAR, config.ALLOW_WRITES_VAR):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(config.CREDENTIALS_DIR_VAR, str(tmp_path / "credentials"))
