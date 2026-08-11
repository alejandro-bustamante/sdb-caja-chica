"""Repository for restock batches and their stock movements."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from app.db.connection import now, rowid, transaction
from app.domain.types import ExpensePaymentInput
from app.domain.validation import validate_expense_payments


def create_batch(
    conn: sqlite3.Connection,
    items: list[tuple[int, int]],
    expense_payments: Sequence[ExpensePaymentInput] | None,
    expense_description: str | None,
    user_id: int,
) -> int:
    """Create a restock batch, its optional expense, items, and stock movements.

    One transaction (AGENTS.md §4): the batch must never exist without its
    stock movements. ``items`` is a list of ``(product_id, quantity)``.
    If ``expense_payments`` is non-empty, a linked ``expenses`` row (version 1)
    is created to record the money leaving the register (split by method).
    """
    with transaction(conn) as _:
        expense_logical_id = None
        if expense_payments:
            expense_logical_id = _insert_new_expense(
                conn, expense_description or "", expense_payments, user_id
            )

        cur = conn.execute(
            "INSERT INTO batches (timestamp, user_id, expense_logical_id)"
            " VALUES (?, ?, ?)",
            (now(), user_id, expense_logical_id),
        )
        batch_id = rowid(cur)

        for product_id, quantity in items:
            cur = conn.execute(
                "INSERT INTO batch_items (batch_id, product_id, quantity)"
                " VALUES (?, ?, ?)",
                (batch_id, product_id, quantity),
            )
            batch_item_id = rowid(cur)
            conn.execute(
                "INSERT INTO stock_movements (product_id, quantity_delta,"
                " timestamp, user_id, batch_item_id, reason)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    product_id,
                    quantity,
                    now(),
                    user_id,
                    batch_item_id,
                    "restock",
                ),
            )
    return batch_id


def _insert_new_expense(
    conn: sqlite3.Connection,
    description: str,
    payments: Sequence[ExpensePaymentInput],
    user_id: int,
) -> int:
    amount = validate_expense_payments(payments)
    logical_id = conn.execute(
        "SELECT COALESCE(MAX(logical_id), 0) + 1 AS next FROM expenses"
    ).fetchone()["next"]
    cur = conn.execute(
        "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
        " description, amount) VALUES (?, 1, ?, ?, ?, ?)",
        (int(logical_id), now(), user_id, description, amount),
    )
    expense_id = rowid(cur)
    for payment in payments:
        conn.execute(
            "INSERT INTO expense_payments (expense_id, method, amount)"
            " VALUES (?, ?, ?)",
            (expense_id, payment.method, payment.amount),
        )
    return int(logical_id)


def resolve_batch_expense(
    conn: sqlite3.Connection, expense_logical_id: int
) -> sqlite3.Row | None:
    """Resolve an expense reference to its current non-deleted version.

    ``batches.expense_logical_id`` is a reference to the expense's *logical_id*
    (see schema.sql). Since that id is not unique across versions, callers must
    resolve it here at read time to the latest non-deleted version.
    """
    return conn.execute(
        "SELECT * FROM expenses WHERE logical_id = ? AND deleted_at IS NULL"
        " AND superseded_at IS NULL ORDER BY version DESC LIMIT 1",
        (expense_logical_id,),
    ).fetchone()


def is_batch_expense_deleted(
    conn: sqlite3.Connection, expense_logical_id: int
) -> bool:
    """Whether an expense reference points at a soft-deleted expense.

    Distinguishes a batch that never had an expense linked
    (``expense_logical_id`` is NULL — ``resolve_batch_expense`` returns None)
    from one whose linked expense was later soft-deleted (also returns None
    from ``resolve_batch_expense``). Callers should use this when they need to
    tell "never billed" apart from "gasto eliminado".
    """
    row = conn.execute(
        "SELECT deleted_at FROM expenses WHERE logical_id = ?"
        " ORDER BY version DESC LIMIT 1",
        (expense_logical_id,),
    ).fetchone()
    return row is not None and row["deleted_at"] is not None


def list_recent_batches(
    conn: sqlite3.Connection, limit: int | None = None
) -> list[sqlite3.Row]:
    """Restock batches, most recent first, with the acting user's name."""
    sql = """
        SELECT b.id, b.timestamp, b.user_id, u.name AS user_name,
               b.expense_logical_id
        FROM batches b
        JOIN users u ON u.id = b.user_id
        ORDER BY b.timestamp DESC
    """
    params: list = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def get_batch_items(conn: sqlite3.Connection, batch_id: int) -> list[sqlite3.Row]:
    """A batch's items, each with its product name for display."""
    return conn.execute(
        "SELECT bi.product_id, p.name AS product_name, bi.quantity"
        " FROM batch_items bi"
        " JOIN products p ON p.id = bi.product_id"
        " WHERE bi.batch_id = ? ORDER BY bi.id",
        (batch_id,),
    ).fetchall()


def find_batch_for_expense(
    conn: sqlite3.Connection, expense_logical_id: int
) -> sqlite3.Row | None:
    """Reverse lookup: does any batch reference this expense logical id?

    Used by the expenses screen to badge batch-linked rows and by the
    Plan #3 Excel export's "linked to restock" column.
    """
    return conn.execute(
        "SELECT id, timestamp, expense_logical_id FROM batches"
        " WHERE expense_logical_id = ? ORDER BY timestamp DESC LIMIT 1",
        (expense_logical_id,),
    ).fetchone()
