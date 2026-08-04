"""Repository for restock batches and their stock movements."""

from __future__ import annotations

import sqlite3

from app.db.connection import now, rowid, transaction


def create_batch(
    conn: sqlite3.Connection,
    items: list[tuple[int, int]],
    expense_amount: int | None,
    expense_description: str | None,
    user_id: int,
) -> int:
    """Create a restock batch, its optional expense, items, and stock movements.

    One transaction (AGENTS.md §4): the batch must never exist without its
    stock movements. ``items`` is a list of ``(product_id, quantity)``.
    If ``expense_amount`` is provided, a linked ``expenses`` row (version 1)
    is created to record the money leaving the register.
    """
    with transaction(conn) as _:
        expense_logical_id = None
        if expense_amount is not None:
            expense_logical_id = _insert_new_expense(
                conn, expense_description or "", expense_amount, user_id
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
    conn: sqlite3.Connection, description: str, amount: int, user_id: int
) -> int:
    logical_id = conn.execute(
        "SELECT COALESCE(MAX(logical_id), 0) + 1 AS next FROM expenses"
    ).fetchone()["next"]
    conn.execute(
        "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
        " description, amount) VALUES (?, 1, ?, ?, ?, ?)",
        (int(logical_id), now(), user_id, description, amount),
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
