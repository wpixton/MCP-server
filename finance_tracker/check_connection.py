"""Sign in to Google (first time only) and confirm the server can see your sheet.

Run from the project folder, with FINANCE_SHEET_ID set:
    python -m finance_tracker.check_connection                  read-only sign-in (token.json)
    python -m finance_tracker.check_connection --allow-writes   separate read-write sign-in (token_write.json)

The read-write sign-in is only needed if you want add_transaction to write to
your real sheet (that also needs FINANCE_ALLOW_REAL_WRITES=yes).

It prints only the spreadsheet title and its tab names/sizes. It asks Google for
those properties alone, so no cell values (amounts, balances, payees) are ever
downloaded.
"""

import sys

from googleapiclient.errors import HttpError

from . import config, google_sheets

# Only sheet *properties*. Cell data lives under sheets.data, which we never request.
STRUCTURE_ONLY = "properties.title,sheets.properties(title,gridProperties(rowCount,columnCount))"


def main(args: list[str] | None = None) -> int:
    write = "--allow-writes" in (sys.argv[1:] if args is None else args)
    token_path = config.write_token_file() if write else config.token_file()

    sheet_id = config.sheet_id()
    if sheet_id is None:
        print(f"{config.SHEET_ID_VAR} is not set, so the server would use the fake sample tracker.")
        print("To check your real sheet, set it first, for example in PowerShell:")
        print(f'    $env:{config.SHEET_ID_VAR} = "<your sheet ID or link>"')
        return 1

    if write:
        print("Signing in with permission to EDIT your spreadsheets (used only by add_transaction).")
    try:
        service = google_sheets.sheets_service(interactive=True, write=write)
        info = service.spreadsheets().get(spreadsheetId=sheet_id, fields=STRUCTURE_ONLY).execute()
    except google_sheets.SetupError as error:
        print(f"Setup needed: {error}")
        return 1
    except HttpError as error:
        if error.resp.status in (403, 404):
            print("Google refused access to that sheet. Check that the ID is right and that you")
            print("signed in with the Google account that owns (or can open) the sheet.")
            print(f"To sign in as a different account, delete {token_path} and run this again.")
            return 1
        raise

    print(f"Connected to: {info['properties']['title']}")
    print(f"Sign-in saved to: {token_path}")
    if write and not config.real_writes_allowed():
        print(f"Note: add_transaction still won't write to this sheet until {config.ALLOW_WRITES_VAR}=yes.")
    print("Tabs:")
    for sheet in info["sheets"]:
        props = sheet["properties"]
        grid = props["gridProperties"]
        print(f"  - {props['title']:<14} {grid['rowCount']:>5} rows x {grid['columnCount']} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
