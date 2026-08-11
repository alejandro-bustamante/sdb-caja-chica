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


def list_cash_counts(
    conn: sqlite3.Connection, limit: int | None = None
) -> list[sqlite3.Row]:
    """Cash-count snapshots, most recent first, with the acting user's name."""
    sql = """
        SELECT cc.id, cc.timestamp, cc.user_id, cc.counted_cash, cc.expected_cash,
               cc.difference, cc.note, u.name AS user_name
        FROM cash_counts cc
        JOIN users u ON u.id = cc.user_id
        ORDER BY cc.timestamp DESC
    """
    params: list = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()
