"""Where the tracker's raw cells come from.

Two sources with the same small interface:

    source.read([(sheet, "A3:H4999"), ...]) -> one list of rows per range

- XlsxSource reads an .xlsx file (the fake sample, by default).
- GoogleSheetSource reads the real Google Sheet through the Sheets API.

Sources don't interpret anything. They hand back raw cell values, and
tracker.py turns those into clean objects. That way both sources go through
the same parsing and the same rules, and can never disagree.
"""

from pathlib import Path

import openpyxl
from openpyxl.utils.cell import range_boundaries

from . import config, google_sheets


class XlsxSource:
    """Reads ranges from an .xlsx file."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def describe(self) -> str:
        return f"sample workbook {self.path.name}"

    def read(self, ranges: list[tuple[str, str]]) -> list[list[list]]:
        # Load, copy the values out, and close right away, so we never hold
        # the file open (Windows would block Excel from saving it).
        wb = openpyxl.load_workbook(self.path)
        try:
            return [self._read_range(wb[sheet], cells) for sheet, cells in ranges]
        finally:
            wb.close()

    @staticmethod
    def _read_range(ws, cells: str) -> list[list]:
        min_col, min_row, max_col, max_row = range_boundaries(cells)
        max_row = min(max_row, ws.max_row)  # don't walk thousands of empty rows
        return [list(row) for row in ws.iter_rows(min_row=min_row, max_row=max_row,
                                                  min_col=min_col, max_col=max_col, values_only=True)]


class GoogleSheetSource:
    """Reads ranges from the real Google Sheet, all in one API request."""

    def __init__(self, sheet_id: str, service=None):
        self.sheet_id = sheet_id
        self._service = service  # tests pass a stand-in; normally created on first use

    def describe(self) -> str:
        return "your Google Sheet"

    def read(self, ranges: list[tuple[str, str]]) -> list[list[list]]:
        service = self._service or google_sheets.sheets_service()
        response = service.spreadsheets().values().batchGet(
            spreadsheetId=self.sheet_id,
            ranges=[f"'{sheet}'!{cells}" for sheet, cells in ranges],  # quotes handle "Net Worth"
            valueRenderOption="UNFORMATTED_VALUE",  # raw numbers, not "$1,234.00"
            dateTimeRenderOption="SERIAL_NUMBER",  # dates as day counts; tracker.py converts them
        ).execute()
        # Google leaves out empty trailing cells and rows; tracker.py handles ragged rows.
        return [value_range.get("values", []) for value_range in response["valueRanges"]]


def open_source():
    """The real sheet if FINANCE_SHEET_ID is set, otherwise the fake sample."""
    sheet_id = config.sheet_id()
    if sheet_id:
        return GoogleSheetSource(sheet_id)
    path = config.sample_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Sample tracker not found: {path}\n"
            "Create it with: python -m finance_tracker.sample_tracker"
        )
    return XlsxSource(path)
