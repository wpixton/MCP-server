"""Where the tracker's raw cells come from, and where new rows go.

Two sources with the same small interface:

    source.read([(sheet, "A3:H4999"), ...])  -> one list of rows per range
    source.write(sheet, row, {"A": value, "B": value, ...})

- XlsxSource reads/writes an .xlsx file (the fake sample, by default).
- GoogleSheetSource reads/writes the real Google Sheet through the Sheets API.

Sources don't interpret anything. They move raw cell values in and out;
tracker.py and writer.py decide what those values mean.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
from openpyxl.utils.cell import range_boundaries

from . import config, google_sheets, layout


class WritesNotAllowed(Exception):
    """Writing to the real Google Sheet hasn't been switched on."""


class XlsxSource:
    """Reads and writes ranges in an .xlsx file."""

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

    def write(self, sheet: str, row: int, values: dict) -> None:
        """Set cells on one row and save. Raises PermissionError if Excel has the file open."""
        wb = openpyxl.load_workbook(self.path)
        try:
            ws = wb[sheet]
            for letter, value in values.items():
                cell = ws[f"{letter}{row}"]
                if isinstance(value, Decimal):
                    value = float(value)  # .xlsx stores numbers as floats
                    cell.number_format = layout.MONEY_FORMAT
                elif isinstance(value, date):
                    cell.number_format = layout.DATE_FORMAT
                cell.value = value
            wb.save(self.path)
        finally:
            wb.close()


class GoogleSheetSource:
    """Reads and writes the real Google Sheet. Each read or write is one API request."""

    def __init__(self, sheet_id: str, service=None, write: bool = False):
        self.sheet_id = sheet_id
        self.can_write = write  # True only when opened for add_transaction with writes allowed
        self._service = service  # tests pass a stand-in; normally created on first use

    def describe(self) -> str:
        return "your Google Sheet"

    def service(self):
        if self._service is None:
            self._service = google_sheets.sheets_service(write=self.can_write)
        return self._service

    def read(self, ranges: list[tuple[str, str]]) -> list[list[list]]:
        response = self.service().spreadsheets().values().batchGet(
            spreadsheetId=self.sheet_id,
            ranges=[f"'{sheet}'!{cells}" for sheet, cells in ranges],  # quotes handle "Net Worth"
            valueRenderOption="UNFORMATTED_VALUE",  # raw numbers, not "$1,234.00"
            dateTimeRenderOption="SERIAL_NUMBER",  # dates as day counts; tracker.py converts them
        ).execute()
        # Google leaves out empty trailing cells and rows; tracker.py handles ragged rows.
        return [value_range.get("values", []) for value_range in response["valueRanges"]]

    def write(self, sheet: str, row: int, values: dict) -> None:
        """Set cells on one row, all in one request, as if you had typed them."""
        if not self.can_write:
            raise WritesNotAllowed("This Google Sheet connection was opened read-only.")
        data = [{"range": f"'{sheet}'!{letter}{row}", "values": [[self._cell_value(value)]]}
                for letter, value in values.items()]
        self.service().spreadsheets().values().batchUpdate(
            spreadsheetId=self.sheet_id,
            # USER_ENTERED = treat values like typing: "2026-11-20" becomes a date, "=..." a formula.
            body={"valueInputOption": "USER_ENTERED", "data": data},
        ).execute()

    @staticmethod
    def _cell_value(value):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, date):
            return value.isoformat()
        return "" if value is None else value


def open_source(for_writing: bool = False):
    """The real sheet if FINANCE_SHEET_ID is set, otherwise the fake sample.

    for_writing=True on the real sheet also requires FINANCE_ALLOW_REAL_WRITES=yes.
    """
    sheet_id = config.sheet_id()
    if sheet_id:
        if for_writing and not config.real_writes_allowed():
            raise WritesNotAllowed(
                "Writing to your real Google Sheet is turned off. To allow it, set "
                f"{config.ALLOW_WRITES_VAR}=yes and sign in for writing once with: "
                f"{google_sheets.SIGN_IN_COMMAND} --allow-writes"
            )
        return GoogleSheetSource(sheet_id, write=for_writing)
    path = config.sample_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Sample tracker not found: {path}\n"
            "Create it with: python -m finance_tracker.sample_tracker"
        )
    return XlsxSource(path)
