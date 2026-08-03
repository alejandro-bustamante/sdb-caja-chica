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
        expense_id = None
        if expense_amount is not None:
            expense_id = _insert_new_expense(
                conn, expense_description or "", expense_amount, user_id
            )

        cur = conn.execute(
            "INSERT INTO batches (timestamp, user_id, expense_id)"
            " VALUES (?, ?, ?)",
            (now(), user_id, expense_id),
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
    cur = conn.execute(
        "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
        " description, amount) VALUES (?, 1, ?, ?, ?, ?)",
        (int(logical_id), now(), user_id, description, amount),
    )
    return rowid(cur)
