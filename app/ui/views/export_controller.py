"""Pure controller logic for the Excel export screen — no Flet imports.

Date parsing/range validation lives here (plan-03 Task 7 exit criteria: the
date-range validation is covered by a controller test, not by the view).

Dates are accepted day-first in several pragmatic spellings the shop user
actually types: separators can be ``/``, ``-``, ``.`` or whitespace, day/month
may be 1 or 2 digits, and the year may be 2 digits (mapped to 20YY) or 4.
"""

from __future__ import annotations

import re
from datetime import date

from app.ui import strings_es

_DIVIDERS = re.compile(r"[/\-.\s]+")


def parse_date_text(text: str | None) -> date | None:
    """Parse a typed ``dd/mm/aaaa``-style value into a date, or ``None``.

    Accepted examples: ``10/09/2026``, ``10/09/26``, ``10-09-2026``,
    ``10.09.26``, ``10 09 2026``. A 2-digit year is treated as 20YY.
    Returns ``None`` for unparseable or impossible dates (e.g. 31/02).
    """
    s = (text or "").strip()
    if not s:
        return None
    parts = [p for p in _DIVIDERS.split(s) if p]
    if len(parts) != 3:
        return None
    day_text, month_text, year_text = parts
    try:
        day, month = int(day_text), int(month_text)
    except ValueError:
        return None
    if len(year_text) == 2:
        year_text = "20" + year_text
    if len(year_text) != 4:
        return None
    try:
        year = int(year_text)
    except ValueError:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def validate_range(
    from_text: str | None, to_text: str | None
) -> tuple[date | None, date | None, str | None]:
    """Validate the export's date range; ``(from, to, message_or_None)``.

    Both dates are required and ``from`` must not be after ``to``.
    """
    date_from = parse_date_text(from_text)
    date_to = parse_date_text(to_text)
    if date_from is None or date_to is None:
        return date_from, date_to, strings_es.EXPORT_INVALID_DATE
    if date_from > date_to:
        return date_from, date_to, strings_es.EXPORT_RANGE_ERROR
    return date_from, date_to, None


def default_file_name(date_from: date, date_to: date) -> str:
    """Suggested workbook filename for the save dialog."""
    return strings_es.EXPORT_FILE_NAME.format(
        date_from=date_from.strftime("%d-%m-%Y"),
        date_to=date_to.strftime("%d-%m-%Y"),
    )
