"""Repository for the ``expenses`` table (versioned, append-only)."""

from __future__ import annotations

import sqlite3

from app.db.connection import now, rowid, transaction


def _next_logical_id(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(logical_id), 0) + 1 AS next FROM expenses"
    ).fetchone()
    return int(row["next"])


def _next_version(conn: sqlite3.Connection, logical_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM expenses"
        " WHERE logical_id = ?",
        (logical_id,),
    ).fetchone()
    return int(row["next"])


def _current_expense_row(conn: sqlite3.Connection, logical_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM expenses WHERE logical_id = ?"
        " ORDER BY version DESC LIMIT 1",
        (logical_id,),
    ).fetchone()


def create_expense(
    conn: sqlite3.Connection, description: str, amount: int, user_id: int
) -> int:
    """Create an expense (version 1) and return its row id."""
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
            " description, amount) VALUES (?, 1, ?, ?, ?, ?)",
            (_next_logical_id(conn), now(), user_id, description, amount),
        )
        return rowid(cur)


def edit_expense(
    conn: sqlite3.Connection,
    logical_id: int,
    description: str,
    amount: int,
    user_id: int,
) -> int:
    """Insert a new version of an expense, superseding the previous one."""
    with transaction(conn):
        old = _current_expense_row(conn, logical_id)
        if old is None:
            raise ValueError(f"Expense logical_id {logical_id} does not exist.")
        conn.execute(
            "UPDATE expenses SET superseded_at = ? WHERE id = ?",
            (now(), old["id"]),
        )
        cur = conn.execute(
            "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
            " description, amount) VALUES (?, ?, ?, ?, ?, ?)",
            (
                logical_id,
                _next_version(conn, logical_id),
                now(),
                user_id,
                description,
                amount,
            ),
        )
        return rowid(cur)


def void_expense(
    conn: sqlite3.Connection, logical_id: int, user_id: int
) -> int:
    """Insert a new version marked as deleted (soft delete)."""
    with transaction(conn):
        old = _current_expense_row(conn, logical_id)
        if old is None:
            raise ValueError("Expense logical_id {logical_id} does not exist.")
        if old["deleted_at"] is not None:
            return int(old["id"])
        conn.execute(
            "UPDATE expenses SET superseded_at = ? WHERE id = ?",
            (now(), old["id"]),
        )
        cur = conn.execute(
            "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
            " description, amount, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                logical_id,
                _next_version(conn, logical_id),
                now(),
                user_id,
                old["description"],
                old["amount"],
                now(),
            ),
        )
        return rowid(cur)


def get_current_expense(conn: sqlite3.Connection, logical_id: int) -> sqlite3.Row | None:
    return _current_expense_row(conn, logical_id)
