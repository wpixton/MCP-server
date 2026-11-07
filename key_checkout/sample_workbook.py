"""Generate a FAKE sample key checkout workbook.

The workbook has the same sheets, columns, formulas, dropdowns and colors as the
real Helaman Halls template, but every person, ID, phone number, hook # and cut #
is made up. Phone numbers use 555-01xx, a range reserved for fiction.

Run it from the project folder:
    python -m key_checkout.sample_workbook              -> sample_data/sample_key_checkout.xlsx
    python -m key_checkout.sample_workbook other.xlsx   -> a new file somewhere else

The log is built relative to "now": two weeks of returned checkouts, three keys
left out on earlier days (OVERDUE), and some activity today, some of it still
out. Re-run the script whenever you want "today" to be today again.
"""

import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from . import layout
from .config import SAMPLE_WORKBOOK

# ---------------------------------------------------------------------------
# Fake data
# ---------------------------------------------------------------------------

FAKE_PEOPLE = [  # (name, dept) -- all invented
    ("Avery Thompson", "Maintenance"),
    ("Jordan Ellis", "Custodial"),
    ("Riley Nakamura", "Electrical"),
    ("Morgan Castillo", "Plumbing"),
    ("Quinn Holloway", "HVAC"),
    ("Parker Adeyemi", "Maintenance"),
    ("Hayden Brooks", "Locksmith"),
    ("Rowan Fitzgerald", "Painting"),
    ("Emerson Vale", "Custodial"),
    ("Sawyer Lindqvist", "Electrical"),
    ("Dakota Reyes", "Grounds"),
    ("Kendall Moss", "Maintenance"),
]

DESK_STAFF = ["Alex", "Jordan", "Sam", "Casey"]  # front desk attendants (first names only)

NOTE_IDEAS = [
    "Work order 48213",
    "Leak in 3rd floor laundry room",
    "Fire alarm inspection",
    "Replacing hallway light fixtures",
    "Annual filter change",
]


def make_people(today: date) -> list[dict]:
    """Fake rows for the People sheet. Keys are layout.PEOPLE field names."""
    people = []
    for i, (name, dept) in enumerate(FAKE_PEOPLE, start=1):
        people.append({
            "scan_id": f"7000{i:06d}",  # what the card reader types when they tap
            "name": name,
            "byu_id": f"99{i:07d}",  # 9 digits, like a BYU ID
            "phone": f"801-555-01{i:02d}",
            "dept": dept,
            "signature_on_file": "No" if i % 4 == 0 else "Yes",
            "date_added": today - timedelta(days=30 + 3 * i),
        })
    return people


def make_keys(rng: random.Random) -> list[dict]:
    """Fake rows for the Keys sheet: the 27 real key ids, with made-up hook and cut numbers."""
    hooks = rng.sample(range(1, 100), len(layout.ALL_KEYS))  # unique hook numbers
    keys = []
    for key_id, hook in zip(layout.ALL_KEYS, hooks):
        letter, set_number = key_id[0], int(key_id[1:])
        keys.append({
            "key": key_id,
            "letter": letter,
            "building": layout.BUILDINGS[letter],
            "set_number": set_number,
            "hook": hook,
            "cut": rng.randint(1000, 9999),
        })
    return keys


def make_log_entries(people: list[dict], now: datetime, rng: random.Random) -> list[dict]:
    """Fake Log rows, oldest first. Keys are layout.LOG field names.

    Only the columns a desk attendant types are filled in. The formula columns
    (name, phone, building name, status...) are left to Excel.
    """
    today = now.date()
    past_days = previous_weekdays(today, 10)  # oldest first
    entries = []

    # Decide up front which keys will still be out at the end, so the story is
    # consistent: 3 keys left out on earlier days (OVERDUE) and 2 out today.
    still_out = rng.sample(layout.ALL_KEYS, 5)
    overdue_keys, out_today_keys = still_out[:3], still_out[3:]
    overdue_since = {
        overdue_keys[0]: past_days[-1],  # 1 weekday ago
        overdue_keys[1]: past_days[-2],  # 2 weekdays ago
        overdue_keys[2]: past_days[-4],  # 4 weekdays ago
    }

    # 1) History: each past weekday a few keys go out and come back the same day.
    for day in past_days:
        # A key that's sitting out overdue can't be checked out again.
        unavailable = {key for key, since in overdue_since.items() if since <= day}
        available = [key for key in layout.ALL_KEYS if key not in unavailable]
        for key in rng.sample(available, rng.randint(2, 4)):
            out = random_moment(rng, at(day, 7, 30), at(day, 14, 30))
            back = out + timedelta(minutes=rng.randint(20, 240))
            entries.append(check_in(rng, people, checkout(rng, people, key, out), back))

    # 2) Overdue: went out on an earlier day and never came back.
    for key, day in overdue_since.items():
        entries.append(checkout(rng, people, key, random_moment(rng, at(day, 8, 0), at(day, 13, 0))))

    # 3) Today: two keys already came back, two are still out. (Skipped if the
    #    script runs before the desk would have had time to issue anything.)
    day_start = at(today, 7, 30)
    if now >= day_start + timedelta(minutes=30):
        free_today = [key for key in layout.ALL_KEYS if key not in still_out]
        for key in rng.sample(free_today, 2):
            out = random_moment(rng, day_start, now - timedelta(minutes=20))
            back = random_moment(rng, out + timedelta(minutes=10), now)
            entries.append(check_in(rng, people, checkout(rng, people, key, out), back))
        for key in out_today_keys:
            entries.append(checkout(rng, people, key, random_moment(rng, day_start, now)))

    # A real log is written top to bottom as keys go out.
    entries.sort(key=lambda e: (e["date_out"], e["time_out"]))
    return entries


def checkout(rng: random.Random, people: list[dict], key: str, out: datetime) -> dict:
    """One Log row as it looks right after a key is issued."""
    person = rng.choice(people)
    # Most people tap their card. Now and then someone forgot it and the
    # attendant typed their BYU ID instead -- the lookup accepts either.
    scan_id = person["byu_id"] if rng.random() < 0.15 else person["scan_id"]
    entry = {
        "scan_id": scan_id,
        "building": key[0],
        "set_number": int(key[1:]),
        "date_out": out.date(),
        "time_out": out.time(),
        "issued_by": rng.choice(DESK_STAFF),
    }
    if rng.random() < 0.25:
        entry["notes"] = rng.choice(NOTE_IDEAS)
    return entry


def check_in(rng: random.Random, people: list[dict], entry: dict, back: datetime) -> dict:
    """Fill in the return columns of a Log row."""
    entry["date_returned"] = back.date()
    entry["time_returned"] = back.time()
    entry["checked_in_by"] = rng.choice(DESK_STAFF)
    if rng.random() < 0.1:  # occasionally a coworker drops the key off
        entry["returned_by"] = rng.choice(people)["name"]
    return entry


def previous_weekdays(today: date, count: int) -> list[date]:
    """The `count` Mon-Fri dates before `today`, oldest first."""
    days = []
    day = today
    while len(days) < count:
        day -= timedelta(days=1)
        if day.weekday() < 5:  # 0-4 = Monday-Friday
            days.append(day)
    return list(reversed(days))


def at(day: date, hour: int, minute: int) -> datetime:
    return datetime.combine(day, time(hour, minute))


def random_moment(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """A random whole minute between start and end (Ctrl+Shift+; has no seconds)."""
    minutes = max(0, int((end - start).total_seconds() // 60))
    return (start + timedelta(minutes=rng.randint(0, minutes))).replace(second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Formulas -- copied from the real template. {r} is the row number.
# ---------------------------------------------------------------------------

def people_lookup(column: str, if_not_found: str) -> str:
    """Look up the scanned value in People column A (card); if that fails, column C (BYU ID)."""
    return (
        '=IF($A{r}="","",'
        f"IFERROR(INDEX(People!${column}$2:${column}$501,MATCH($A{{r}},People!$A$2:$A$501,0)),"
        f"IFERROR(INDEX(People!${column}$2:${column}$501,MATCH($A{{r}},People!$C$2:$C$501,0)),"
        f'"{if_not_found}")))'
    )


LOG_FORMULAS = {
    "B": people_lookup("B", "NOT FOUND - add to People"),
    "C": people_lookup("C", ""),
    "D": people_lookup("D", ""),
    "E": people_lookup("E", ""),
    "H": '=IF(F{r}="","",IFERROR(INDEX(Keys!$C$2:$C$28,MATCH(F{r},Keys!$B$2:$B$28,0)),"bad letter"))',
    "I": '=IF(OR(F{r}="",G{r}=""),"",IFERROR(INDEX(Keys!$E$2:$E$28,MATCH(F{r}&G{r},Keys!$A$2:$A$28,0))&"",""))',
    "J": '=IF(OR(F{r}="",G{r}=""),"",IFERROR(INDEX(Keys!$F$2:$F$28,MATCH(F{r}&G{r},Keys!$A$2:$A$28,0))&"",""))',
    "R": (
        '=IF(AND(A{r}="",F{r}=""),"",IF(N{r}<>"","Returned",'
        'IF(COUNTIFS($F$2:$F$1501,F{r},$G$2:$G$1501,G{r},$N$2:$N$1501,"",$A$2:$A$1501,"<>")>1,"CHECK: key already out",'
        'IF(K{r}="","Out (no date entered)",IF(NOW()>K{r}+TIME(17,0,0),"OVERDUE","Out")))))'
    ),
}

# Key Board: {r} is the board row (6-32), {k} is the matching Keys row (2-28).
BOARD_FORMULAS = {
    "A": "=Keys!A{k}",
    "B": "=Keys!C{k}",
    "C": "=Keys!D{k}",
    "D": '=IF(K{r}="","In",INDEX(Log!R:R,K{r}))',
    "E": '=IF($K{r}="","",INDEX(Log!B:B,$K{r})&"")',
    "F": '=IF($K{r}="","",INDEX(Log!E:E,$K{r})&"")',
    "G": '=IF($K{r}="","",INDEX(Log!D:D,$K{r})&"")',
    "H": '=IF($K{r}="","",IF(INDEX(Log!K:K,$K{r})="","",INDEX(Log!K:K,$K{r})))',
    "I": '=IF($K{r}="","",IF(INDEX(Log!L:L,$K{r})="","",INDEX(Log!L:L,$K{r})))',
    "J": '=IF($K{r}="","",INDEX(Log!M:M,$K{r})&"")',
    # Finds the Log row where this key is out: last row matching letter + set with no return date.
    "K": (
        '=IFERROR(LOOKUP(2,1/((Log!$F$2:$F$1501=Keys!B{k})*(Log!$G$2:$G$1501=Keys!D{k})'
        '*(Log!$N$2:$N$1501="")*(Log!$R$2:$R$1501<>"")),ROW(Log!$F$2:$F$1501)),"")'
    ),
}

# ---------------------------------------------------------------------------
# Styling -- colors match the real template
# ---------------------------------------------------------------------------

NAVY = "1F3864"
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")
AUTO_FILL = PatternFill("solid", fgColor="EDEDED")  # grey = formula column, don't type here
AUTO_FONT = Font(color="595959")
WHITE_FILL = PatternFill("solid", fgColor="FFFFFF")
DATE_FORMAT = "m/d/yy"
TIME_FORMAT = "h:mm AM/PM"
TEXT_FORMAT = "@"  # keeps IDs as text so leading zeros survive


def solid(color: str) -> PatternFill:
    return PatternFill(start_color=color, end_color=color, fill_type="solid")


OVERDUE_FILL = solid("F8CBAD")  # red
CHECK_FILL = solid("FFD966")  # gold
OUT_FILL = solid("FFF2CC")  # yellow
RED_TEXT = Font(bold=True, color="C00000")
GREEN_TEXT = Font(color="548235")


def write_headers(ws, columns: list[tuple], widths: dict[str, float], row: int = 1) -> None:
    for letter, header, _field in columns:
        cell = ws[f"{letter}{row}"]
        cell.value = header
        cell.font, cell.fill, cell.alignment = HEADER_FONT, HEADER_FILL, HEADER_ALIGN
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width


def list_dropdown(ws, cell_range: str, choices: str) -> None:
    dv = DataValidation(type="list", formula1=f'"{choices}"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(cell_range)


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def add_log_sheet(wb: Workbook, entries: list[dict]) -> None:
    ws = wb.create_sheet(layout.LOG_SHEET)
    write_headers(ws, layout.LOG_COLUMNS, {
        "A": 18, "B": 26.2, "C": 13, "D": 14, "F": 9, "G": 7, "H": 13, "I": 8, "J": 7,
        "K": 15, "M": 11, "N": 15, "P": 12, "Q": 13, "R": 22, "S": 24,
    })
    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "B2"

    # Like the template: every row down to 1501 has its formulas and formatting
    # ready, so the desk only types in the white cells.
    for r in range(layout.FIRST_DATA_ROW, layout.LOG_LAST_ROW + 1):
        for letter, _header, _field in layout.LOG_COLUMNS:
            cell = ws[f"{letter}{r}"]
            if letter in LOG_FORMULAS:
                cell.value = LOG_FORMULAS[letter].format(r=r)
                cell.fill, cell.font = AUTO_FILL, AUTO_FONT
            else:
                cell.fill = WHITE_FILL
        ws[f"A{r}"].number_format = TEXT_FORMAT
        for letter in ("K", "N"):
            ws[f"{letter}{r}"].number_format = DATE_FORMAT
        for letter in ("L", "O"):
            ws[f"{letter}{r}"].number_format = TIME_FORMAT

    # Now type the fake checkouts into the white cells, top to bottom.
    for r, entry in enumerate(entries, start=layout.FIRST_DATA_ROW):
        for field, value in entry.items():
            ws[f"{layout.LOG[field]}{r}"] = value

    list_dropdown(ws, "F2:F1501", ",".join(layout.BUILDINGS))
    list_dropdown(ws, "G2:G1501", ",".join(str(n) for n in layout.SET_NUMBERS))

    cf = ws.conditional_formatting
    cf.add("A2:S1501", FormulaRule(formula=['$R2="OVERDUE"'], fill=OVERDUE_FILL))
    cf.add("A2:S1501", FormulaRule(formula=['LEFT($R2,5)="CHECK"'], fill=CHECK_FILL))
    cf.add("B2:B1501", FormulaRule(formula=['LEFT($B2,9)="NOT FOUND"'], font=RED_TEXT))
    cf.add("R2:R1501", FormulaRule(formula=['LEFT($R2,3)="Out"'], fill=OUT_FILL))
    cf.add("R2:R1501", FormulaRule(formula=['$R2="Returned"'], font=GREEN_TEXT))


def add_people_sheet(wb: Workbook, people: list[dict]) -> None:
    ws = wb.create_sheet(layout.PEOPLE_SHEET)
    write_headers(ws, layout.PEOPLE_COLUMNS, {"A": 20, "B": 24, "C": 14, "D": 16, "F": 12, "H": 30})
    ws.freeze_panes = "A2"
    for r in range(layout.FIRST_DATA_ROW, layout.PEOPLE_LAST_ROW + 1):
        for letter in ("A", "C", "D"):
            ws[f"{letter}{r}"].number_format = TEXT_FORMAT
        ws[f"G{r}"].number_format = DATE_FORMAT
    for r, person in enumerate(people, start=layout.FIRST_DATA_ROW):
        for field, value in person.items():
            ws[f"{layout.PEOPLE[field]}{r}"] = value
    list_dropdown(ws, "F2:F501", "Yes,No")


def add_keys_sheet(wb: Workbook, keys: list[dict]) -> None:
    ws = wb.create_sheet(layout.KEYS_SHEET)
    write_headers(ws, layout.KEYS_COLUMNS, {"A": 8, "C": 14, "D": 7, "E": 10, "F": 8})
    for r, key in enumerate(keys, start=layout.FIRST_DATA_ROW):
        for field, value in key.items():
            ws[f"{layout.KEYS[field]}{r}"] = value
    ws["H2"] = "Sample data: hook and cut numbers are made up."


def add_key_board_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet(layout.BOARD_SHEET)
    ws["A1"] = "Helaman Halls - Maintenance Keys"
    ws["A1"].font = Font(bold=True, size=16, color=NAVY)
    ws["A2"] = "Updates automatically from the Log tab. Press F9 to refresh overdue status."
    ws["A2"].font = Font(size=10, color="595959")
    ws["A3"], ws["B3"] = "Keys out:", '=COUNTIF(D6:D32,"<>In")'
    ws["C3"], ws["D3"] = "Overdue:", '=COUNTIF(D6:D32,"OVERDUE")'
    for ref in ("A3", "B3", "C3", "D3"):
        ws[ref].font = Font(bold=True)

    headers = ["Key", "Building", "Set #", "Status", "Checked Out To", "Dept",
               "Phone", "Date Out", "Time Out", "Issued By", "log row"]
    columns = [(letter, header, None) for letter, header in zip("ABCDEFGHIJK", headers)]
    write_headers(ws, columns, {"A": 7, "B": 13, "C": 7, "D": 22, "F": 14, "H": 10, "J": 11, "K": 8}, row=5)
    for letter, _header, _ in columns:
        ws[f"{letter}5"].font = Font(bold=True, size=10, color="FFFFFF")

    for i in range(len(layout.ALL_KEYS)):
        r, k = 6 + i, 2 + i  # board row 6 shows Keys row 2, and so on
        for letter, formula in BOARD_FORMULAS.items():
            cell = ws[f"{letter}{r}"]
            cell.value = formula.format(r=r, k=k)
            cell.font = Font(size=10)
        ws[f"H{r}"].number_format = DATE_FORMAT
        ws[f"I{r}"].number_format = TIME_FORMAT
        ws[f"K{r}"].font = Font(size=8, color="A6A6A6")  # helper column, greyed out
    ws.freeze_panes = "A6"

    cf = ws.conditional_formatting
    cf.add("A6:J32", FormulaRule(formula=['$D6="OVERDUE"'], fill=OVERDUE_FILL))
    cf.add("A6:J32", FormulaRule(formula=['LEFT($D6,5)="CHECK"'], fill=CHECK_FILL))
    cf.add("A6:J32", FormulaRule(formula=['LEFT($D6,3)="Out"'], fill=OUT_FILL))
    cf.add("D6:D32", FormulaRule(formula=['$D6="In"'], font=GREEN_TEXT))
    cf.add("D3", FormulaRule(formula=["$D$3>0"], font=RED_TEXT))


HOW_TO = [  # (style, text) -- same instructions as the real template
    ("title", "How to use the key log"),
    ("", ""),
    ("heading", "CHECKING A KEY OUT  (Log tab, first empty row)"),
    ("", "1. Click the Scan ID / Card cell and have them tap their BYU ID on the reader."),
    ("", "   Name, BYU ID, phone and dept fill in by themselves. If you see NOT FOUND, add them on the People tab (see below)."),
    ("", "2. Pick the Building letter and Set # from the dropdowns. Building name, hook # and cut # fill in."),
    ("", "3. Date Out: press Ctrl+;     Time Out: press Ctrl+Shift+;     Issued By: your name."),
    ("", "4. They still sign the paper sheet (or confirm their signature is on file)."),
    ("", ""),
    ("heading", "CHECKING A KEY IN"),
    ("", "1. Find the key on the Key Board tab - the 'log row' column (far right) tells you which Log row it's on."),
    ("", "2. On that Log row: Date Returned = Ctrl+;   Time Returned = Ctrl+Shift+;   Checked In By = your name."),
    ("", "3. Fill 'Returned By' only if someone other than the original person brought it back."),
    ("", ""),
    ("heading", "NEW MAINTENANCE PERSON  (People tab)"),
    ("", "Click the first empty Scan ID / Card cell, have them tap their card, then fill in name, BYU ID, phone and dept."),
    ("", "Their row on the Log tab fills in right away. You only do this once per person."),
    ("", ""),
    ("heading", "STATUS COLORS"),
    ("", "Yellow = out     Red = OVERDUE (not back by 5 PM the day it went out)     Gold = CHECK: the same key shows out on two rows."),
    ("", "Overdue status updates whenever the file recalculates; press F9 to force it."),
    ("", ""),
    ("heading", "TIPS"),
    ("", "- Grey columns are automatic - don't type in them. White columns are for you."),
    ("", "- Forgot their card? Type their BYU ID in the Scan cell instead; it still looks them up."),
    ("", "- Dept is pulled from People. If they're working for a different dept today, just type over it on that row."),
    ("", "- If the reader adds an Enter after the number, the cursor drops down a row - just click back to the Building cell."),
    ("", "- This is a SAMPLE workbook: every person, ID and phone number in it is fictional."),
]


def add_how_to_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet(layout.HOWTO_SHEET)
    ws.column_dimensions["A"].width = 110
    for r, (style, text) in enumerate(HOW_TO, start=1):
        ws[f"A{r}"] = text or None
        if style == "title":
            ws[f"A{r}"].font = Font(bold=True, size=16)
        elif style == "heading":
            ws[f"A{r}"].font = Font(bold=True)


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------

def build_sample_workbook(path: Path = SAMPLE_WORKBOOK, now: datetime | None = None, seed: int = 42) -> Path:
    """Write a fake workbook to `path` and return the path.

    `now` and `seed` make the output repeatable: the same values always give the
    same workbook, which is what the tests rely on.

    As a safety net it refuses to overwrite any existing file except this repo's
    own sample workbook, so it can never clobber a real key log by accident.
    """
    path = Path(path)
    if path.exists() and path.resolve() != SAMPLE_WORKBOOK.resolve():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")

    now = now or datetime.now()
    rng = random.Random(seed)
    people = make_people(now.date())
    keys = make_keys(rng)
    entries = make_log_entries(people, now, rng)

    wb = Workbook()
    wb.remove(wb.active)  # drop the default empty "Sheet"
    add_key_board_sheet(wb)
    add_log_sheet(wb, entries)
    add_people_sheet(wb, people)
    add_keys_sheet(wb, keys)
    add_how_to_sheet(wb)
    wb.active = 0  # open on the Key Board, like the template
    # openpyxl can't calculate formulas, so ask Excel to calculate everything on open.
    wb.calculation.fullCalcOnLoad = True

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE_WORKBOOK
    path = build_sample_workbook(out)
    print(f"Wrote fake sample workbook to {path}")


if __name__ == "__main__":
    main()
