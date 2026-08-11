"""Repository for products and their append-only price history."""

from __future__ import annotations

import sqlite3

from app.db.connection import now, rowid, transaction
from app.domain.types import ProductWithCurrentPrice

_CURRENT_PRICE_SQL = """
    SELECT price
    FROM product_prices
    WHERE product_id = :product_id
      AND superseded_at IS NULL
    ORDER BY valid_from DESC
    LIMIT 1
"""


def create_product(
    conn: sqlite3.Connection, name: str, initial_price: int, user_id: int
) -> int:
    """Create a product and its first price row in one transaction."""
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO products (name, active) VALUES (?, 1)", (name,)
        )
        product_id = rowid(cur)
        conn.execute(
            "INSERT INTO product_prices (product_id, price, valid_from,"
            " user_id) VALUES (?, ?, ?, ?)",
            (product_id, initial_price, now(), user_id),
        )
    return product_id


def _current_price(conn: sqlite3.Connection, product_id: int) -> int | None:
    row = conn.execute(
        "SELECT price FROM product_prices"
        " WHERE product_id = :product_id AND superseded_at IS NULL"
        " ORDER BY valid_from DESC LIMIT 1",
        {"product_id": product_id},
    ).fetchone()
    return None if row is None else int(row["price"])


def _to_product_views(
    conn: sqlite3.Connection, rows
) -> list[ProductWithCurrentPrice]:
    return [
        ProductWithCurrentPrice(
            id=int(r["id"]),
            name=r["name"],
            active=bool(r["active"]),
            current_price=_current_price(conn, int(r["id"])),
        )
        for r in rows
    ]


def list_active_products(conn: sqlite3.Connection) -> list[ProductWithCurrentPrice]:
    rows = conn.execute(
        "SELECT id, name, active FROM products WHERE active = 1 ORDER BY name"
    ).fetchall()
    return _to_product_views(conn, rows)


def list_all_products(conn: sqlite3.Connection) -> list[ProductWithCurrentPrice]:
    """Every product, active or not, so the catalog can show/reactivate."""
    rows = conn.execute(
        "SELECT id, name, active FROM products ORDER BY name"
    ).fetchall()
    return _to_product_views(conn, rows)


def update_product_price(
    conn: sqlite3.Connection,
    product_id: int,
    new_price: int,
    user_id: int,
    reason: str | None = None,
) -> int:
    """Append a new price row and supersede the previous one.

    Never overwrites an old price value — it only marks the current row
    superseded and inserts the new one (AGENTS.md §1).
    """
    with transaction(conn):
        conn.execute(
            "UPDATE product_prices SET superseded_at = ?"
            " WHERE product_id = ? AND superseded_at IS NULL",
            (now(), product_id),
        )
        cur = conn.execute(
            "INSERT INTO product_prices (product_id, price, valid_from,"
            " user_id, reason) VALUES (?, ?, ?, ?, ?)",
            (product_id, new_price, now(), user_id, reason),
        )
        return rowid(cur)


def set_product_active(
    conn: sqlite3.Connection, product_id: int, active: bool, user_id: int
) -> None:
    """Toggle a product's `active` visibility flag.

    Decision (flagged for review, not silent): toggling `active` is treated as
    a simple mutable flag on the reference-style `products` row, NOT a
    versioned business fact — it is a visibility toggle, not a correction of
    historical data. `user_id` is accepted to keep call sites uniform, though
    no user field is persisted for a plain visibility flag.
    """
    with conn:
        conn.execute(
            "UPDATE products SET active = ? WHERE id = ?", (int(active), product_id)
        )
