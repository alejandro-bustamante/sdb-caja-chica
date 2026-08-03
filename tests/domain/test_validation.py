"""Tests for domain/validation.py (Task 3.2)."""

from __future__ import annotations

import pytest

from app.domain.types import SaleItemInput, SalePaymentInput
from app.domain.validation import (
    CreditSaleWithPayments,
    NonCreditSaleWithoutPayments,
    PartialPaymentTooLarge,
    PaymentTotalMismatch,
    validate_partial_payment,
    validate_sale_payments,
)

ITEM_10 = SaleItemInput(product_id=1, quantity=2, unit_price_applied=500)  # 1000
ITEM_5 = SaleItemInput(product_id=2, quantity=1, unit_price_applied=500)  # 500

CASH_1500 = SalePaymentInput(method="cash", amount=1500)


def test_cash_sale_matches_exactly():
    validate_sale_payments([ITEM_10, ITEM_5], [CASH_1500], is_credit=False)


def test_split_payment_matches():
    validate_sale_payments(
        [ITEM_10],
        [SalePaymentInput("cash", 600), SalePaymentInput("qr", 400)],
        is_credit=False,
    )


def test_non_credit_sale_without_payments_raises():
    with pytest.raises(NonCreditSaleWithoutPayments):
        validate_sale_payments([ITEM_10], [], is_credit=False)


def test_payment_mismatch_raises():
    with pytest.raises(PaymentTotalMismatch):
        validate_sale_payments(
            [ITEM_10], [SalePaymentInput("cash", 900)], is_credit=False
        )


def test_credit_sale_rejects_upfront_payments():
    with pytest.raises(CreditSaleWithPayments):
        validate_sale_payments([ITEM_10], [CASH_1500], is_credit=True)


def test_credit_sale_with_no_payments_ok():
    validate_sale_payments([ITEM_10], [], is_credit=True)


def test_partial_payment_ok():
    validate_partial_payment(300, remaining_balance=500)


def test_partial_payment_totals_balance_ok():
    validate_partial_payment(500, remaining_balance=500)


def test_partial_payment_over_balance_raises():
    with pytest.raises(PartialPaymentTooLarge):
        validate_partial_payment(501, remaining_balance=500)


def test_partial_payment_non_positive_raises():
    with pytest.raises(PartialPaymentTooLarge):
        validate_partial_payment(0, remaining_balance=500)
