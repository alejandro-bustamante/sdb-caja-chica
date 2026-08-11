"""Repository for the ``expenses`` table (versioned, append-only) and its
per-version payment split (``expense_payments``)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from app.db.connection import now, rowid, transaction
from app.domain.types import ExpensePaymentInput
from app.domain.validation import validate_expense_payments


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


def _serialize_payments(
    conn: sqlite3.Connection, expense_id: int, payments: Sequence[ExpensePaymentInput]
) -> None:
    for payment in payments:
        conn.execute(
            "INSERT INTO expense_payments (expense_id, method, amount)"
            " VALUES (?, ?, ?)",
            (expense_id, payment.method, payment.amount),
        )


def create_expense(
    conn: sqlite3.Connection,
    description: str,
    payments: Sequence[ExpensePaymentInput],
    user_id: int,
) -> int:
    """Create an expense (version 1) and return its row id.

    ``expenses.amount`` is derived as the sum of the payment split, so it can
    never drift from what was actually paid. The expense's effect on balance is
    always read from ``expense_payments`` by method (balance.py), not from the
    amount column.
    """
    amount = validate_expense_payments(payments)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
            " description, amount) VALUES (?, 1, ?, ?, ?, ?)",
            (_next_logical_id(conn), now(), user_id, description, amount),
        )
        expense_id = rowid(cur)
        _serialize_payments(conn, expense_id, payments)
        return expense_id


def edit_expense(
    conn: sqlite3.Connection,
    logical_id: int,
    description: str,
    payments: Sequence[ExpensePaymentInput],
    user_id: int,
) -> int:
    """Insert a new version of an expense, superseding the previous one."""
    amount = validate_expense_payments(payments)
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
        expense_id = rowid(cur)
        _serialize_payments(conn, expense_id, payments)
        return expense_id


def void_expense(
    conn: sqlite3.Connection, logical_id: int, user_id: int
) -> int:
    """Insert a new version marked as deleted (soft delete).

    The voided version carries no payments, mirroring ``void_sale`` — the
    current version is soft-deleted, so the expense stops counting against
    balance either way.
    """
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


def get_expense_payments(
    conn: sqlite3.Connection, expense_id: int
) -> list[sqlite3.Row]:
    """An expense version's payment rows, in insertion order."""
    return conn.execute(
        "SELECT method, amount FROM expense_payments"
        " WHERE expense_id = ? ORDER BY id",
        (expense_id,),
    ).fetchall()


def list_current_expenses(
    conn: sqlite3.Connection, limit: int | None = None
) -> list[sqlite3.Row]:
    """Current (latest non-deleted) expense versions, most recent first,
    with the acting user's name."""
    sql = """
        SELECT e.id, e.logical_id, e.version, e.timestamp, e.user_id,
               e.description, e.amount, u.name AS user_name
        FROM expenses e
        JOIN users u ON u.id = e.user_id
        JOIN (
            SELECT logical_id, MAX(version) AS max_version
            FROM expenses GROUP BY logical_id
        ) latest
          ON latest.logical_id = e.logical_id
         AND latest.max_version = e.version
        WHERE e.deleted_at IS NULL
        ORDER BY e.timestamp DESC
    """
    params: list = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()
