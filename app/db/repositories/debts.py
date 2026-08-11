"""Repository for credit-sale debts (fiado collections)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.connection import now, rowid, transaction
from app.domain.validation import validate_partial_payment


@dataclass(frozen=True)
class OpenDebt:
    logical_id: int
    customer_name: str | None
    total: int
    paid: int

    @property
    def outstanding(self) -> int:
        return self.total - self.paid


def _current_sale_row(conn: sqlite3.Connection, logical_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sales WHERE logical_id = ? ORDER BY version DESC LIMIT 1",
        (logical_id,),
    ).fetchone()


def _sale_total(conn: sqlite3.Connection, sale_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COALESCE(SUM(quantity * unit_price_applied), 0) AS total"
            " FROM sale_items WHERE sale_id = ?",
            (sale_id,),
        ).fetchone()["total"]
    )


def _paid_for_logical(conn: sqlite3.Connection, logical_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COALESCE(SUM(dp.amount), 0) AS total"
            " FROM debt_payments dp"
            " JOIN sales s ON s.id = dp.sale_id"
            " WHERE s.logical_id = ?",
            (logical_id,),
        ).fetchone()["total"]
    )


def _outstanding(conn: sqlite3.Connection, sale: sqlite3.Row) -> int:
    return _sale_total(conn, sale["id"]) - _paid_for_logical(conn, sale["logical_id"])


def list_open_debts(conn: sqlite3.Connection) -> list[OpenDebt]:
    rows = conn.execute(
        """
        SELECT s.logical_id, s.customer_name
        FROM sales s
        WHERE s.is_credit = 1
          AND s.deleted_at IS NULL
          AND s.version = (
            SELECT MAX(version) FROM sales s2 WHERE s2.logical_id = s.logical_id
          )
        ORDER BY s.logical_id
        """
    ).fetchall()
    debts: list[OpenDebt] = []
    for r in rows:
        logical_id = int(r["logical_id"])
        sale = _current_sale_row(conn, logical_id)
        assert sale is not None
        total = _sale_total(conn, sale["id"])
        paid = _paid_for_logical(conn, logical_id)
        if paid < total:
            debts.append(
                OpenDebt(
                    logical_id=logical_id,
                    customer_name=r["customer_name"],
                    total=total,
                    paid=paid,
                )
            )
    return debts


def mark_debt_paid(conn: sqlite3.Connection, sale_logical_id: int, user_id: int) -> int:
    """Insert one debt-payment row covering the full outstanding balance."""
    sale = _current_sale_row(conn, sale_logical_id)
    if sale is None:
        raise ValueError("Credit sale does not exist.")
    return _record_payment(conn, sale, _outstanding(conn, sale), user_id)


def list_settled_debts(
    conn: sqlite3.Connection, limit: int | None = None
) -> list[OpenDebt]:
    """Credit sales fully paid off, most recent first (read-only history)."""
    rows = conn.execute(
        """
        SELECT s.logical_id, s.customer_name
        FROM sales s
        WHERE s.is_credit = 1
          AND s.deleted_at IS NULL
          AND s.version = (
            SELECT MAX(version) FROM sales s2 WHERE s2.logical_id = s.logical_id
          )
        ORDER BY s.timestamp DESC
        """
    ).fetchall()
    settled: list[OpenDebt] = []
    for r in rows:
        logical_id = int(r["logical_id"])
        sale = _current_sale_row(conn, logical_id)
        assert sale is not None
        total = _sale_total(conn, sale["id"])
        paid = _paid_for_logical(conn, logical_id)
        if paid >= total:
            settled.append(
                OpenDebt(
                    logical_id=logical_id,
                    customer_name=r["customer_name"],
                    total=total,
                    paid=paid,
                )
            )
    if limit is not None:
        settled = settled[:limit]
    return settled


def record_partial_payment(
    conn: sqlite3.Connection, sale_logical_id: int, amount: int, user_id: int
) -> int:
    """Record a partial (or full) debt collection on a credit sale."""
    sale = _current_sale_row(conn, sale_logical_id)
    if sale is None:
        raise ValueError("Credit sale does not exist.")
    outstanding = _outstanding(conn, sale)
    validate_partial_payment(amount, outstanding)
    return _record_payment(conn, sale, amount, user_id)


def _record_payment(
    conn: sqlite3.Connection, sale: sqlite3.Row, amount: int, user_id: int
) -> int:
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO debt_payments (sale_id, amount, timestamp, user_id)"
            " VALUES (?, ?, ?, ?)",
            (sale["id"], amount, now(), user_id),
        )
        return rowid(cur)
