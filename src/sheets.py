"""Google Sheets adapter using a service account.

Workflow:
  1. Read all rows
  2. Process those whose 'status' column is empty or 'pending'
  3. Write enriched fields back to the same row
  4. Update 'status' to 'done' or 'error'
"""
from __future__ import annotations
import logging
from typing import Iterable, List, Optional, Tuple

from .config import GOOGLE_APPLICATION_CREDENTIALS, LEADS_SHEET_ID, LEADS_WORKSHEET_NAME
from .models import EnrichedLead, INPUT_COLUMNS, Lead, OUTPUT_COLUMNS

log = logging.getLogger(__name__)

# Rows whose status is one of these are considered work to do.
_PENDING_STATES = {"", "pending", "retry"}


def _open_sheet():
    if not GOOGLE_APPLICATION_CREDENTIALS:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS env var is not set; cannot open sheet"
        )
    if not LEADS_SHEET_ID:
        raise RuntimeError("LEADS_SHEET_ID env var is not set; cannot open sheet")
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        GOOGLE_APPLICATION_CREDENTIALS, scopes=scopes,
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(LEADS_SHEET_ID)
    try:
        ws = sh.worksheet(LEADS_WORKSHEET_NAME)
    except Exception:
        ws = sh.sheet1
    return ws


def ensure_header(ws) -> None:
    """Ensure the sheet has the expected header row. Writes it if the sheet is empty."""
    values = ws.get_all_values()
    if not values:
        ws.update(values=[OUTPUT_COLUMNS], range_name="A1")
        return
    header = values[0]
    missing = [c for c in INPUT_COLUMNS if c not in header]
    if missing:
        raise RuntimeError(
            f"Sheet header missing required input columns: {missing}. "
            f"Expected at minimum: {INPUT_COLUMNS}"
        )
    # Extend the header with any output columns that are not yet present
    appended = False
    for col in OUTPUT_COLUMNS:
        if col not in header:
            header.append(col)
            appended = True
    if appended:
        ws.update(values=[header], range_name="A1")


def read_pending_leads(ws) -> List[Tuple[int, Lead]]:
    """Return [(row_number, Lead)] for rows whose status is empty or 'pending'."""
    values = ws.get_all_values()
    if not values:
        return []
    header = values[0]
    idx = {col: header.index(col) for col in header}

    leads: List[Tuple[int, Lead]] = []
    for i, row in enumerate(values[1:], start=2):  # row 1 is header
        def cell(col: str) -> str:
            j = idx.get(col)
            return (row[j].strip() if j is not None and j < len(row) else "")

        status = cell("status").lower()
        if status not in _PENDING_STATES:
            continue
        if not cell("person_email") or not cell("company"):
            continue
        leads.append((
            i,
            Lead(
                person_name=cell("person_name"),
                person_email=cell("person_email"),
                company=cell("company"),
                property_address=cell("property_address"),
                city=cell("city"),
                state=cell("state"),
                country=cell("country") or "US",
            ),
        ))
    return leads


def write_enriched(ws, row_number: int, enriched: EnrichedLead) -> None:
    """Update a single sheet row with enriched output."""
    header = ws.row_values(1)
    row_dict = enriched.to_row()
    # Build an ordered row that matches the current sheet header
    ordered: List[str] = []
    for col in header:
        v = row_dict.get(col, "")
        ordered.append(str(v) if v is not None else "")
    # Write the whole row at once
    end_col_letter = _col_letter(len(header))
    ws.update(values=[ordered], range_name=f"A{row_number}:{end_col_letter}{row_number}")


def mark_status(ws, row_number: int, status: str, error_summary: str = "") -> None:
    header = ws.row_values(1)
    try:
        status_col = header.index("status") + 1
    except ValueError:
        return
    ws.update_cell(row_number, status_col, status)
    if error_summary:
        try:
            err_col = header.index("error_summary") + 1
            ws.update_cell(row_number, err_col, error_summary)
        except ValueError:
            pass


def _col_letter(col_num: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA."""
    out = ""
    n = col_num
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out
