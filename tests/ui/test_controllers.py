"""Tests for catalog / restock / expenses / debts / cash-count controllers."""

from __future__ import annotations

from app.domain.types import ExpensePaymentInput
from app.ui import strings_es
from app.ui.views import (
    cash_counts_controller,
    catalog_controller,
    debts_controller,
    expenses_controller,
    restock_controller,
)

# --- catalog ----------------------------------------------------------------

def test_catalog_create_form_error():
    assert catalog_controller.create_form_error("", "100") == strings_es.CATALOG_EMPTY_NAME
    assert catalog_controller.create_form_error("Azúcar", "abc") == strings_es.CATALOG_INVALID_PRICE
    assert catalog_controller.create_form_error("Azúcar", "") == strings_es.CATALOG_INVALID_PRICE
    assert catalog_controller.create_form_error("Azúcar", "100") is None


def test_catalog_update_price_error():
    assert catalog_controller.update_price_error("x") == strings_es.CATALOG_INVALID_PRICE
    assert catalog_controller.update_price_error("") == strings_es.CATALOG_INVALID_PRICE
    assert catalog_controller.update_price_error("0") is None
    assert catalog_controller.update_price_error("12.50") is None


# --- restock ----------------------------------------------------------------

def test_restock_add_line_error():
    assert restock_controller.add_line_error(None, "2") == strings_es.RESTOCK_NEED_PRODUCT
    assert restock_controller.add_line_error(1, "abc") == strings_es.RESTOCK_INVALID_QUANTITY
    assert restock_controller.add_line_error(1, "2") is None


def test_restock_expense_payments_error():
    assert restock_controller.expense_payments_error("", "") is None
    assert restock_controller.expense_payments_error(None, None) is None
    assert restock_controller.expense_payments_error("0", "") == strings_es.RESTOCK_INVALID_EXPENSE
    assert restock_controller.expense_payments_error("abc", "") == strings_es.RESTOCK_INVALID_EXPENSE
    assert restock_controller.expense_payments_error("150.50", "") is None
    # Empty cash+QR -> no linked expense; any value -> parsed split.
    assert restock_controller.build_expense_payments("", "") == []
    built = restock_controller.build_expense_payments("150.50", "25")
    assert built == [ExpensePaymentInput("cash", 15050), ExpensePaymentInput("qr", 2500)]


def test_restock_line_summary():
    assert restock_controller.line_summary("Azúcar", 10) == "Azúcar x10"


# --- expenses ---------------------------------------------------------------

def test_expenses_create_form_error():
    assert expenses_controller.create_form_error("", "100", "") == strings_es.EXPENSES_EMPTY_DESC
    assert expenses_controller.create_form_error("Luz", "", "") == strings_es.EXPENSES_NO_PAYMENT
    assert expenses_controller.create_form_error("Luz", "0", "") == strings_es.EXPENSES_NO_PAYMENT
    assert expenses_controller.create_form_error("Luz", "abc", "") == strings_es.EXPENSES_INVALID_AMOUNT
    assert expenses_controller.create_form_error("Luz", "8000", "") is None
    assert expenses_controller.create_form_error("Luz", "", "500") is None
    assert expenses_controller.create_form_error("Luz", "100", "200") is None


def test_expenses_build_payments():
    assert expenses_controller.build_payments("10", "20") == [
        ExpensePaymentInput("cash", 1000),
        ExpensePaymentInput("qr", 2000),
    ]
    assert expenses_controller.build_payments("", "20") == [ExpensePaymentInput("qr", 2000)]
    assert expenses_controller.build_payments("", "") is None


def test_expenses_void_warning():
    assert expenses_controller.void_warning(False) == strings_es.EXPENSES_VOID_WARNING
    assert expenses_controller.void_warning(True) == strings_es.EXPENSES_VOID_BATCH_WARNING


# --- debts ------------------------------------------------------------------

def test_debts_abono_error():
    assert debts_controller.abono_error("", 5000) == strings_es.DEBTS_INVALID_ABONO
    assert debts_controller.abono_error("abc", 5000) == strings_es.DEBTS_INVALID_ABONO
    assert debts_controller.abono_error("0", 5000) == strings_es.DEBTS_INVALID_ABONO
    too_big = debts_controller.abono_error("51", 5000)
    assert too_big == strings_es.DEBTS_ABONO_TOO_LARGE.format(outstanding="50.00")
    assert debts_controller.abono_error("50", 5000) is None
    assert debts_controller.abono_error("30", 5000) is None


# --- cash counts ------------------------------------------------------------

def test_counted_cash_error():
    assert cash_counts_controller.counted_cash_error("") == strings_es.ARQUEO_INVALID_AMOUNT
    assert cash_counts_controller.counted_cash_error("-5") == strings_es.ARQUEO_INVALID_AMOUNT
    assert cash_counts_controller.counted_cash_error("10.50") is None
    assert cash_counts_controller.counted_cash_error("0") is None


def test_counted_parsing():
    assert cash_counts_controller.parse_counted("10.50") == 1050
    assert cash_counts_controller.parse_counted("0") == 0
    assert cash_counts_controller.parse_counted("-1") is None
    assert cash_counts_controller.parse_counted("") is None


def test_result_message():
    match = cash_counts_controller.result_message(1000, 1000)
    assert match == strings_es.ARQUEO_RESULT_MATCH.format(counted="10.00", expected="10.00")
    over = cash_counts_controller.result_message(1300, 1000)
    assert over == strings_es.ARQUEO_RESULT_OVER.format(
        diff="3.00", counted="13.00", expected="10.00"
    )
    short = cash_counts_controller.result_message(800, 1000)
    assert short == strings_es.ARQUEO_RESULT_SHORT.format(
        diff="2.00", counted="8.00", expected="10.00"
    )
