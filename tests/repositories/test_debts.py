"""Tests for repositories.debts (fiado collections)."""

from __future__ import annotations

import pytest

from app.db.repositories import batches, debts, sales
from app.db.repositories.products import create_product
from app.domain.balance import compute_available_cash
from app.domain.types import SaleItemInput
from app.domain.validation import PartialPaymentTooLarge


def _credit_sale(conn, user_id: int) -> int:
    pid = create_product(conn, "Azúcar", 1000, user_id)
    batches.create_batch(conn, [(pid, 10)], None, None, user_id)
    sales.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1000)],
        [],
        True,
        "Pepe",
        "some note",
        user_id,
    )
    return pid


def test_open_debts_initial(conn, user_id):
    _credit_sale(conn, user_id)
    debts_list = debts.list_open_debts(conn)
    assert len(debts_list) == 1
    assert debts_list[0].total == 2000
    assert debts_list[0].paid == 0


def test_partial_payment(conn, user_id):
    _credit_sale(conn, user_id)
    debts.record_partial_payment(conn, 1, 700, user_id)
    (debt,) = debts.list_open_debts(conn)
    assert debt.paid == 700
    assert debt.outstanding == 1300
    assert compute_available_cash(conn) == 700


def test_partial_payment_over_balance_rejected(conn, user_id):
    _credit_sale(conn, user_id)
    with pytest.raises(PartialPaymentTooLarge):
        debts.record_partial_payment(conn, 1, 999999, user_id)


def test_mark_debt_paid_closes_debt(conn, user_id):
    _credit_sale(conn, user_id)
    debts.record_partial_payment(conn, 1, 500, user_id)
    debts.mark_debt_paid(conn, 1, user_id)
    assert debts.list_open_debts(conn) == []
    assert compute_available_cash(conn) == 2000
