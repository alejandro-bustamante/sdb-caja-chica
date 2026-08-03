"""Repository for sales (versioned, append-only headers + items + payments).

Every edit / void / reassignment inserts a brand-new sales row and rebuilds
the version's own shelf of items, payments, and stock movements, so the net
stock effect and money effect of a ``logical_id`` always reflect only its
current (non-deleted) version. Old rows are never touched except for setting
``superseded_at`` (AGENTS.md §1, §4).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from app.db.connection import now, rowid, transaction
from app.domain.types import SaleItemInput, SalePaymentInput
from app.domain.validation import validate_sale_payments


def _next_logical_id(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            "SELECT COALESCE(MAX(logical_id), 0) + 1 AS next FROM sales"
        ).fetchone()["next"]
    )


def _next_version(conn: sqlite3.Connection, logical_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM sales"
            " WHERE logical_id = ?",
            (logical_id,),
        ).fetchone()["next"]
    )


def _current_sale_row(conn: sqlite3.Connection, logical_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sales WHERE logical_id = ? ORDER BY version DESC LIMIT 1",
        (logical_id,),
    ).fetchone()


def _supersede(conn: sqlite3.Connection, sale_id: int) -> None:
    conn.execute("UPDATE sales SET superseded_at = ? WHERE id = ?", (now(), sale_id))


def _reverse_sale_stock(conn: sqlite3.Connection, sale_id: int, user_id: int) -> None:
    """Undo a sales version's stock by inserting opposite movements.

    Reversals reference the same ``sale_item_id`` they undo, so the ledger
    stays traceable. Net stock of the *logical_id* therefore reflects only
    the current version after an edit/void.
    """
    rows = conn.execute(
        "SELECT sale_item_id, SUM(quantity_delta) AS net"
        " FROM stock_movements WHERE sale_item_id IN ("
        "    SELECT id FROM sale_items WHERE sale_id = ?)"
        " GROUP BY sale_item_id",
        (sale_id,),
    ).fetchall()
    for r in rows:
        if r["net"] == 0:
            continue
        product_id = conn.execute(
            "SELECT product_id FROM stock_movements WHERE sale_item_id = ? LIMIT 1",
            (r["sale_item_id"],),
        ).fetchone()["product_id"]
        conn.execute(
            "INSERT INTO stock_movements (product_id, quantity_delta,"
            " timestamp, user_id, sale_item_id, reason)"
            " VALUES (?, ?, ?, ?, ?, 'sale-reverse')",
            (product_id, -r["net"], now(), user_id, r["sale_item_id"]),
        )


def _serialize_items(conn: sqlite3.Connection, sale_id: int, items, user_id: int) -> None:
    for item in items:
        cur = conn.execute(
            "INSERT INTO sale_items (sale_id, product_id, quantity,"
            " unit_price_applied, price_manually_overridden)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                sale_id,
                item.product_id,
                item.quantity,
                item.unit_price_applied,
                int(item.price_manually_overridden),
            ),
        )
        sale_item_id = rowid(cur)
        conn.execute(
            "INSERT INTO stock_movements (product_id, quantity_delta,"
            " timestamp, user_id, sale_item_id, reason)"
            " VALUES (?, ?, ?, ?, ?, 'sale')",
            (item.product_id, -item.quantity, now(), user_id, sale_item_id),
        )


def _serialize_payments(conn: sqlite3.Connection, sale_id: int, payments) -> None:
    for payment in payments:
        conn.execute(
            "INSERT INTO sale_payments (sale_id, method, amount)"
            " VALUES (?, ?, ?)",
            (sale_id, payment.method, payment.amount),
        )


def _validate_new(items, payments, is_credit: bool, customer_name: str | None) -> None:
    validate_sale_payments(items, payments, is_credit)
    if is_credit and customer_name is None:
        raise ValueError("A credit sale requires a customer name.")


def _insert_header(
    conn: sqlite3.Connection,
    logical_id: int,
    version: int,
    registered_by_user: int,
    current_user: int,
    is_credit: bool,
    customer_name: str | None,
    customer_note: str | None,
    deleted_at: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO sales (logical_id, version, timestamp,"
        " registered_by_user, current_user, is_credit, customer_name,"
        " customer_note, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            logical_id,
            version,
            now(),
            registered_by_user,
            current_user,
            int(is_credit),
            customer_name,
            customer_note,
            deleted_at,
        ),
    )
    return rowid(cur)


def create_sale(
    conn: sqlite3.Connection,
    items: Sequence[SaleItemInput],
    payments: Sequence[SalePaymentInput],
    is_credit: bool,
    customer_name: str | None,
    customer_note: str | None,
    user_id: int,
) -> int:
    """Create a sale (version 1), validating payments before any write."""
    _validate_new(items, payments, is_credit, customer_name)
    with transaction(conn):
        sale_id = _insert_header(
            conn,
            _next_logical_id(conn),
            version=1,
            registered_by_user=user_id,
            current_user=user_id,
            is_credit=is_credit,
            customer_name=customer_name,
            customer_note=customer_note,
        )
        _serialize_items(conn, sale_id, items, user_id)
        _serialize_payments(conn, sale_id, payments)
    return sale_id


def edit_sale(
    conn: sqlite3.Connection,
    logical_id: int,
    items: Sequence[SaleItemInput],
    payments: Sequence[SalePaymentInput],
    is_credit: bool,
    customer_name: str | None,
    customer_note: str | None,
    user_id: int,
) -> int:
    """Insert a new sale version, superseding the previous one."""
    _validate_new(items, payments, is_credit, customer_name)
    with transaction(conn):
        old = _current_sale_row(conn, logical_id)
        if old is None:
            raise ValueError("Sale logical_id does not exist.")
        _supersede(conn, old["id"])
        _reverse_sale_stock(conn, old["id"], user_id)
        new_id = _insert_header(
            conn,
            old["logical_id"],
            version=_next_version(conn, logical_id),
            registered_by_user=old["registered_by_user"],
            current_user=user_id,
            is_credit=is_credit,
            customer_name=customer_name,
            customer_note=customer_note,
        )
        _serialize_items(conn, new_id, items, user_id)
        _serialize_payments(conn, new_id, payments)
    return new_id


def void_sale(conn: sqlite3.Connection, logical_id: int, user_id: int) -> int:
    """Insert a versioned soft-delete and reverse the logical's stock."""
    with transaction(conn):
        old = _current_sale_row(conn, logical_id)
        if old is None:
            raise ValueError("Sale logical_id does not exist.")
        if old["deleted_at"] is not None:
            return int(old["id"])
        _supersede(conn, old["id"])
        _reverse_sale_stock(conn, old["id"], user_id)
        return _insert_header(
            conn,
            old["logical_id"],
            version=_next_version(conn, logical_id),
            registered_by_user=old["registered_by_user"],
            current_user=user_id,
            is_credit=bool(old["is_credit"]),
            customer_name=old["customer_name"],
            customer_note=old["customer_note"],
            deleted_at=now(),
        )


def reassign_sale_user(
    conn: sqlite3.Connection, logical_id: int, new_current_user: int, acting_user: int
) -> int:
    """New version with ``current_user`` changed; items/payments/stock preserved."""
    with transaction(conn):
        old = _current_sale_row(conn, logical_id)
        if old is None:
            raise ValueError("Sale logical_id does not exist.")
        _supersede(conn, old["id"])
        _reverse_sale_stock(conn, old["id"], acting_user)
        old_items = conn.execute(
            "SELECT product_id, quantity, unit_price_applied,"
            " price_manually_overridden FROM sale_items WHERE sale_id = ?",
            (old["id"],),
        ).fetchall()
        old_payments = conn.execute(
            "SELECT method, amount FROM sale_payments WHERE sale_id = ?",
            (old["id"],),
        ).fetchall()
        new_id = _insert_header(
            conn,
            old["logical_id"],
            version=_next_version(conn, old["logical_id"]),
            registered_by_user=old["registered_by_user"],
            current_user=new_current_user,
            is_credit=bool(old["is_credit"]),
            customer_name=old["customer_name"],
            customer_note=old["customer_note"],
        )
        items = [SaleItemInput(**dict(r)) for r in old_items]
        payments = [SalePaymentInput(**dict(r)) for r in old_payments]
        _serialize_items(conn, new_id, items, acting_user)
        _serialize_payments(conn, new_id, payments)
    return new_id


def get_sale_current(conn: sqlite3.Connection, logical_id: int) -> sqlite3.Row | None:
    row = _current_sale_row(conn, logical_id)
    if row is None or row["deleted_at"] is not None:
        return None
    return row


def get_sale_history(conn: sqlite3.Connection, logical_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sales WHERE logical_id = ? ORDER BY version",
        (logical_id,),
    ).fetchall()
