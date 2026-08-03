"""Repository for cash counts (arqueo) — immutable snapshots."""

from __future__ import annotations

import sqlite3

from app.db.connection import now, rowid, transaction
from app.domain.balance import compute_available_cash


def record_cash_count(
    conn: sqlite3.Connection, counted_cash: int, user_id: int, note: str | None = None
) -> int:
    """Snapshot a cash count with its computed expected value and difference.

    ``expected_cash`` is computed at insertion time and stored on the row.
    Past ``cash_counts`` rows are never recomputed or "fixed" — a discrepancy
    is recorded as-is (DESIGN.md §3.7).
    """
    expected = compute_available_cash(conn)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO cash_counts (timestamp, user_id, counted_cash,"
            " expected_cash, difference, note)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (now(), user_id, counted_cash, expected, counted_cash - expected, note),
        )
        return rowid(cur)
