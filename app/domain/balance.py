"""Derived money/stock calculations — pure SELECTs, never any writes.

Money is stored as integer cents and every computation here uses integer
arithmetic (exact — no floats). The formulas follow DESIGN.md §3.8:

    available_cash = cash_sales + collected_debt_payments - expenses
    available_qr   = qr_sales
    total_available = available_cash + available_qr

Each balance is derived from the underlying ledger tables at query time —
nothing here is ever cached or stored as a mutable value (AGENTS.md §1).
"""

from __future__ import annotations

import sqlite3

_CURRENT_SALE_IDS_SQL = """
SELECT s.id
FROM sales s
JOIN (
    SELECT logical_id, MAX(version) AS max_version
    FROM sales
    {as_of_cond}
    GROUP BY logical_id
) latest
  ON latest.logical_id = s.logical_id
 AND latest.max_version = s.version
WHERE s.deleted_at IS NULL
"""


def _current_sale_ids(conn: sqlite3.Connection, as_of: int | None) -> list[int]:
    if as_of is not None:
        sql = _CURRENT_SALE_IDS_SQL.format(as_of_cond="WHERE timestamp <= ?")
        params: tuple = (as_of,)
    else:
        sql = _CURRENT_SALE_IDS_SQL.format(as_of_cond="")
        params = ()
    return [row["id"] for row in conn.execute(sql, params)]


def _sum_sale_payments(
    conn: sqlite3.Connection, sale_ids: list[int], method: str
) -> int:
    if not sale_ids:
        return 0
    placeholders = ",".join("?" * len(sale_ids))
    row = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS total"
        f" FROM sale_payments"
        f" WHERE method = ? AND sale_id IN ({placeholders})",
        (method, *sale_ids),
    ).fetchone()
    return int(row["total"])


def _sum_current_expenses(conn: sqlite3.Connection, as_of: int | None) -> int:
    as_of_cond = "WHERE timestamp <= ?" if as_of is not None else ""
    sql = f"""
    SELECT COALESCE(SUM(amount), 0) AS total
    FROM expenses e
    JOIN (
        SELECT logical_id, MAX(version) AS max_version
        FROM expenses
        {as_of_cond}
        GROUP BY logical_id
    ) latest
      ON latest.logical_id = e.logical_id
     AND latest.max_version = e.version
    WHERE e.deleted_at IS NULL
    """
    params: tuple = () if as_of is None else (as_of,)
    return int(conn.execute(sql, params).fetchone()["total"])


# No join back to "current sale version" is needed here: sales.py's
# _reject_edited_credit_sale_with_collections guarantees a credit sale can
# never be re-versioned (edited/voided) once it has debt_payments, so every
# debt_payments row is always attached to a sale's one and only version.
# If that guard is ever removed, this function must be revisited.
def _sum_collected_debt_payments(
    conn: sqlite3.Connection, as_of: int | None
) -> int:
    sql = "SELECT COALESCE(SUM(amount), 0) AS total FROM debt_payments"
    params: tuple = ()
    if as_of is not None:
        sql += " WHERE timestamp <= ?"
        params = (as_of,)
    return int(conn.execute(sql, params).fetchone()["total"])


def compute_available_cash(conn: sqlite3.Connection, as_of: int | None = None) -> int:
    """Cash available in the drawer, in integer cents.

    cash_sales + collected debt payments - expenses.
    """
    sale_ids = _current_sale_ids(conn, as_of)
    cash_sales = _sum_sale_payments(conn, sale_ids, "cash")
    collected = _sum_collected_debt_payments(conn, as_of)
    expenses = _sum_current_expenses(conn, as_of)
    return cash_sales + collected - expenses


def compute_available_qr(conn: sqlite3.Connection, as_of: int | None = None) -> int:
    """QR-app money, in integer cents (qr sales only)."""
    sale_ids = _current_sale_ids(conn, as_of)
    return _sum_sale_payments(conn, sale_ids, "qr")


def compute_total_available(conn: sqlite3.Connection, as_of: int | None = None) -> int:
    """Total money available = available cash + available QR, in cents."""
    return compute_available_cash(conn, as_of) + compute_available_qr(conn, as_of)


def compute_expected_cash(conn: sqlite3.Connection) -> int:
    """What the drawer should contain right now — i.e. available cash.

    Used by ``record_cash_count`` to snapshot ``expected_cash``.
    """
    return compute_available_cash(conn)


def compute_current_stock(conn: sqlite3.Connection, product_id: int) -> int:
    """Current stock level of one product: SUM of its signed movements."""
    row = conn.execute(
        "SELECT COALESCE(SUM(quantity_delta), 0) AS stock"
        " FROM stock_movements"
        " WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    return int(row["stock"])


def format_cents(cents: int) -> str:
    """Format integer cents as a currency string for display (monetary only).

    UI-facing wording lives in strings_es.py; this only shapes the number.
    """
    sign = "-" if cents < 0 else ""
    absolute = abs(cents)
    return f"{sign}{absolute // 100}.{absolute % 100:02d}"
