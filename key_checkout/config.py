"""Where is the workbook?

By default the server uses the FAKE sample workbook in this repo. To point it at
a different file (for example the real log on the front desk PC), set the
KEY_CHECKOUT_WORKBOOK environment variable to that file's full path.
"""

import os
from pathlib import Path

ENV_VAR = "KEY_CHECKOUT_WORKBOOK"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_WORKBOOK = PROJECT_ROOT / "sample_data" / "sample_key_checkout.xlsx"


def get_workbook_path() -> Path:
    """Return the workbook path from KEY_CHECKOUT_WORKBOOK, or the sample workbook."""
    value = os.environ.get(ENV_VAR, "").strip().strip('"')  # tolerate a quoted Windows path
    if value:
        return Path(value).expanduser()
    return SAMPLE_WORKBOOK
