"""The workbook's layout: sheet names, columns, buildings.

This is the single source of truth for "where things live" in the key log.
The sample-data generator, the read layer and the write layer all import from
here, so if the real template ever moves a column, there's one place to fix.
"""

# --- Sheet names (in the order they appear in the workbook) ---
BOARD_SHEET = "Key Board"
LOG_SHEET = "Log"
PEOPLE_SHEET = "People"
KEYS_SHEET = "Keys"
HOWTO_SHEET = "How To"

# Row 1 is headers on Log / People / Keys; data starts on row 2.
FIRST_DATA_ROW = 2

# The template comes with formulas pre-filled down to these rows, so a row
# with formulas in it is NOT necessarily "used". A Log row is in use when it
# has a Scan ID (A) or a Building (F) -- the same test the Status formula uses.
LOG_LAST_ROW = 1501
PEOPLE_LAST_ROW = 501

# --- Columns ---
# Each entry is (column letter, header text exactly as in the template, field name).
# Columns marked "formula" are calculated by Excel; openpyxl can't evaluate
# them, so the Python code works those values out itself.
LOG_COLUMNS = [
    ("A", "Scan ID / Card", "scan_id"),
    ("B", "Issued To", "issued_to"),  # formula: People lookup
    ("C", "BYU ID", "byu_id"),  # formula: People lookup
    ("D", "Phone", "phone"),  # formula: People lookup
    ("E", "Dept", "dept"),  # formula: People lookup
    ("F", "Building", "building"),  # letter B-J
    ("G", "Set #", "set_number"),  # 1-3
    ("H", "Building Name", "building_name"),  # formula: Keys lookup
    ("I", "Hook #", "hook"),  # formula: Keys lookup
    ("J", "Cut #", "cut"),  # formula: Keys lookup
    ("K", "Date Out\n(Ctrl + ;)", "date_out"),
    ("L", "Time Out\n(Ctrl + Shift + ;)", "time_out"),
    ("M", "Issued By", "issued_by"),
    ("N", "Date Returned\n(Ctrl + ;)", "date_returned"),
    ("O", "Time Returned\n(Ctrl + Shift + ;)", "time_returned"),
    ("P", "Checked In By", "checked_in_by"),
    ("Q", "Returned By\n(if different)", "returned_by"),
    ("R", "Status", "status"),  # formula: Returned / Out / OVERDUE / ...
    ("S", "Notes", "notes"),
]

PEOPLE_COLUMNS = [
    ("A", "Scan ID / Card", "scan_id"),
    ("B", "Name", "name"),
    ("C", "BYU ID", "byu_id"),
    ("D", "Phone", "phone"),
    ("E", "Dept", "dept"),
    ("F", "Signature on File?", "signature_on_file"),
    ("G", "Date Added", "date_added"),
    ("H", "Notes", "notes"),
]

KEYS_COLUMNS = [
    ("A", "Key", "key"),  # e.g. "F2" = building letter + set number
    ("B", "Letter", "letter"),
    ("C", "Building", "building"),
    ("D", "Set #", "set_number"),
    ("E", "Hook #", "hook"),
    ("F", "Cut #", "cut"),
]

# Handy lookups: LOG["date_out"] -> "K"
LOG = {field: letter for letter, _header, field in LOG_COLUMNS}
PEOPLE = {field: letter for letter, _header, field in PEOPLE_COLUMNS}
KEYS = {field: letter for letter, _header, field in KEYS_COLUMNS}

# --- Buildings and key sets ---
BUILDINGS = {
    "B": "Hinckley",
    "C": "Chipman",
    "D": "David John",
    "E": "Taylor",
    "F": "Stover",
    "G": "Budge",
    "H": "Merrill",
    "I": "May",
    "J": "Building 9",
}
SET_NUMBERS = (1, 2, 3)

# Every key id, in the same order as the Keys sheet: B1, B2, B3, C1, ... J3
ALL_KEYS = [f"{letter}{n}" for letter in BUILDINGS for n in SET_NUMBERS]
