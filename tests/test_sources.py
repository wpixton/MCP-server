"""Tests for sources.py. The Google source uses a stand-in service: no network."""

from datetime import datetime

import pytest

from finance_tracker import config
from finance_tracker.sample_tracker import build_sample_tracker
from finance_tracker.sources import GoogleSheetSource, XlsxSource, open_source

NOW = datetime(2026, 11, 20, 14, 0)


def test_xlsx_source_reads_ranges_and_lets_go_of_the_file(tmp_path):
    path = build_sample_tracker(tmp_path / "tracker.xlsx", now=NOW)
    (headers,) = XlsxSource(path).read([("Expenses", "A2:G2")])
    assert headers == [["Date", "Description", "Category", "Amount", "Account", "Notes", "Month"]]
    path.rename(tmp_path / "moved.xlsx")  # fails on Windows if the file were still open


class StandInService:
    """Mimics service.spreadsheets().values().batchGet(...).execute() and records the call."""

    def __init__(self, response):
        self.response, self.request = response, None

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def batchGet(self, **kwargs):
        self.request = kwargs
        return self

    def execute(self):
        return self.response


def test_google_source_asks_for_raw_values_in_one_request():
    service = StandInService({"valueRanges": [{"values": [[1, 2]]}, {}]})  # 2nd range is empty
    rows = GoogleSheetSource("SHEET", service=service).read([("Income", "A3:H10"), ("Net Worth", "A1:A2")])
    assert rows == [[[1, 2]], []]
    assert service.request["ranges"] == ["'Income'!A3:H10", "'Net Worth'!A1:A2"]
    assert service.request["valueRenderOption"] == "UNFORMATTED_VALUE"
    assert service.request["dateTimeRenderOption"] == "SERIAL_NUMBER"


def test_open_source_uses_the_sample_by_default(monkeypatch, tmp_path):
    path = build_sample_tracker(tmp_path / "tracker.xlsx", now=NOW)
    monkeypatch.setenv(config.SAMPLE_PATH_VAR, str(path))
    source = open_source()
    assert isinstance(source, XlsxSource) and source.path == path


def test_open_source_uses_google_when_a_sheet_id_is_set(monkeypatch):
    monkeypatch.setenv(config.SHEET_ID_VAR, "SHEET")
    source = open_source()  # doesn't connect yet; that happens on the first read
    assert isinstance(source, GoogleSheetSource) and source.sheet_id == "SHEET"


def test_missing_sample_explains_how_to_make_one(monkeypatch, tmp_path):
    monkeypatch.setenv(config.SAMPLE_PATH_VAR, str(tmp_path / "nope.xlsx"))
    with pytest.raises(FileNotFoundError, match="sample_tracker"):
        open_source()
