"""Tests for domain.balance — money and stock are always derived (Task 3.1)."""

from __future__ import annotations

from app.db.repositories import batches, sales
from app.db.repositories.debts import record_partial_payment
from app.db.repositories.products import create_product
from app.domain.balance import (
    compute_available_cash,
    compute_available_qr,
    compute_total_available,
    format_cents,
)
from app.domain.types import SaleItemInput, SalePaymentInput


def _sale(conn, user_id, method, amount, credit=False, customer=None):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    batches.create_batch(conn, [(pid, 10)], None, None, user_id)
    item = SaleItemInput(
        product_id=pid, quantity=1, unit_price_applied=1000 if credit else max(amount, 1)
    )
    return sales.create_sale(
        conn,
        [item],
        [SalePaymentInput(method, amount)] if not credit else [],
        credit,
        customer,
        None,
        user_id,
    )


def test_cash_and_qr_are_separate(conn, user_id):
    _sale(conn, user_id, "cash", 1000)
    _sale(conn, user_id, "qr", 2000)
    assert compute_available_cash(conn) == 1000
    assert compute_available_qr(conn) == 2000
    assert compute_total_available(conn) == 3000


def test_debt_collection_adds_to_cash(conn, user_id):
    _sale(conn, user_id, "n/a", 0, credit=True, customer="Pepe")
    record_partial_payment(conn, 1, 400, user_id)
    # Credit sale contributes no upfront cash until collected.
    assert compute_available_cash(conn) == 400


def test_expense_reduces_total(conn, user_id):
    from app.db.repositories.expenses import create_expense

    _sale(conn, user_id, "cash", 1000)
    create_expense(conn, "Luz", 300, user_id)
    assert compute_total_available(conn) == 700


def test_format_cents():
    assert format_cents(1234) == "12.34"
    assert format_cents(-5) == "-0.05"


def _set_sale_timestamps(conn, logical_id: int, v1_ts: int, v2_ts: int) -> None:
    conn.execute(
        "UPDATE sales SET timestamp = ? WHERE logical_id = ? AND version = 1",
        (v1_ts, logical_id),
    )
    conn.execute(
        "UPDATE sales SET timestamp = ? WHERE logical_id = ? AND version = 2",
        (v2_ts, logical_id),
    )
    conn.commit()


def test_as_of_uses_version_current_at_cutoff_for_sale(conn, user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    batches.create_batch(conn, [(pid, 10)], None, None, user_id)
    v1 = SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1000)
    v2 = SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1000)
    sales.create_sale(conn, [v1], [SalePaymentInput("cash", 1000)], False, None, None, user_id)
    sales.edit_sale(conn, 1, [v2], [SalePaymentInput("cash", 2000)], False, None, None, user_id)
    _set_sale_timestamps(conn, 1, 100, 200)

    assert compute_available_cash(conn) == 2000  # unrestricted -> latest version
    assert compute_available_cash(conn, as_of=150) == 1000  # v1 active at cutoff


def test_as_of_uses_version_current_at_cutoff_for_expense(conn, user_id):
    from app.db.repositories.expenses import create_expense, edit_expense

    create_expense(conn, "Luz", 500, user_id)
    edit_expense(conn, 1, "Luz", 700, user_id)
    conn.execute(
        "UPDATE expenses SET timestamp = 100 WHERE logical_id = 1 AND version = 1"
    )
    conn.execute(
        "UPDATE expenses SET timestamp = 200 WHERE logical_id = 1 AND version = 2"
    )
    conn.commit()

    assert compute_available_cash(conn) == -700
    assert compute_available_cash(conn, as_of=150) == -500
