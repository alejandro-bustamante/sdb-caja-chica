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
from app.domain.validation import ValidationError, validate_sale_payments


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


def _reject_edited_credit_sale_with_collections(
    conn: sqlite3.Connection, sale: sqlite3.Row
) -> None:
    """Refuse to supersede a credit sale that already has debt collections.

    Collections on a credit sale are append-only money rows tied to the sale's
    versions. Re-versioning the sale after money has been collected would make
    ``available_cash`` disagree with the outstanding debt (AGENTS.md §1). A
    negative/rebate payment mechanism is explicitly out of scope, so the safe
    option is to reject the edit/void of a collected credit sale with a
    ``ValidationError``.
    """
    if not bool(sale["is_credit"]):
        return
    collected = conn.execute(
        "SELECT 1 FROM debt_payments dp"
        " JOIN sales s ON s.id = dp.sale_id"
        " WHERE s.logical_id = ?",
        (sale["logical_id"],),
    ).fetchone()
    if collected is not None:
        raise ValidationError(
            "A credit sale with recorded collections cannot be edited."
        )


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
        _reject_edited_credit_sale_with_collections(conn, old)
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
        _reject_edited_credit_sale_with_collections(conn, old)
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


def list_current_sales(
    conn: sqlite3.Connection,
    since_ts: int | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Current (latest non-deleted) sale versions, most recent first.

    ``since_ts`` optionally restricts to sales at or after a timestamp
    (e.g. start of today for the "ventas de hoy" list).
    """
    sql = """
        SELECT s.id, s.logical_id, s.timestamp, s.is_credit, s.customer_name,
               s.customer_note, s.current_user, u.name AS current_user_name,
               EXISTS (
                   SELECT 1 FROM debt_payments dp
                   JOIN sales s2 ON s2.id = dp.sale_id
                   WHERE s2.logical_id = s.logical_id
               ) AS has_collections
        FROM sales s
        JOIN (
            SELECT logical_id, MAX(version) AS max_version
            FROM sales GROUP BY logical_id
        ) latest
          ON latest.logical_id = s.logical_id
         AND latest.max_version = s.version
        JOIN users u ON u.id = s.current_user
        WHERE s.deleted_at IS NULL
    """
    params: list = []
    if since_ts is not None:
        sql += " AND s.timestamp >= ?"
        params.append(since_ts)
    sql += " ORDER BY s.timestamp DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def get_sale_items(conn: sqlite3.Connection, sale_id: int) -> list[sqlite3.Row]:
    """A sale version's items, each with its product name for display."""
    return conn.execute(
        "SELECT si.product_id, p.name AS product_name, si.quantity,"
        " si.unit_price_applied, si.price_manually_overridden"
        " FROM sale_items si"
        " JOIN products p ON p.id = si.product_id"
        " WHERE si.sale_id = ? ORDER BY si.id",
        (sale_id,),
    ).fetchall()


def get_sale_payments(conn: sqlite3.Connection, sale_id: int) -> list[sqlite3.Row]:
    """A sale version's payment rows, in insertion order."""
    return conn.execute(
        "SELECT method, amount FROM sale_payments WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    ).fetchall()
