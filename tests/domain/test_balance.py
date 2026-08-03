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
