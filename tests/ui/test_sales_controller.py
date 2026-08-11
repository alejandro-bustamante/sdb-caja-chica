"""Tests for the sales screen controller (plan Task 8 §1)."""

from __future__ import annotations

from app.domain.types import SalePaymentInput
from app.domain.validation import PaymentTotalMismatch
from app.ui import strings_es
from app.ui.views import sales_controller
from app.ui.views.sales_controller import CartLine, add_cart_line


def _line(price=1000, qty=2, name="Azúcar"):
    return CartLine(product_id=1, name=name, quantity=qty, unit_price=price)


def test_cart_total_and_merge():
    cart = [_line()]
    add_cart_line(cart, 1, "Azúcar", 3, 1000)
    assert len(cart) == 1
    assert cart[0].quantity == 5
    assert sales_controller.cart_total(cart) == 5000


def test_override_price_sets_flag_and_uses_new_price():
    cart = [_line()]
    sales_controller.override_cart_line_price(cart, 0, 1500)
    assert cart[0].overridden is True
    assert cart[0].unit_price == 1500
    items = sales_controller.to_sale_items(cart)
    assert items[0].price_manually_overridden is True
    assert items[0].total == 3000


def test_default_lines_are_not_marked_overridden():
    cart = [_line()]
    items = sales_controller.to_sale_items(cart)
    assert items[0].price_manually_overridden is False


def test_remove_cart_line():
    cart = [_line(), CartLine(2, "Sal", 1, 500)]
    sales_controller.remove_cart_line(cart, 0)
    assert [line.product_id for line in cart] == [2]


def test_add_line_input_error():
    from app.ui.views.common_controller import parse_quantity_input

    assert sales_controller.add_line_input_error(None, "2") == strings_es.SALES_NEED_PRODUCT
    assert (
        sales_controller.add_line_input_error(1, "abc") == strings_es.SALES_INVALID_QUANTITY
    )
    assert parse_quantity_input("2") == 2
    assert sales_controller.add_line_input_error(1, "2") is None


def test_build_payments_from_texts():
    payments, err = sales_controller.build_payments_from_texts("10.00", "5.50")
    assert err is None
    assert payments == [
        SalePaymentInput("cash", 1000),
        SalePaymentInput("qr", 550),
    ]


def test_build_payments_from_texts_invalid():
    payments, err = sales_controller.build_payments_from_texts("abc", None)
    assert payments is None
    assert err == strings_es.SALES_INVALID_AMOUNT
    payments, err = sales_controller.build_payments_from_texts("", "1.234")
    assert payments is None
    assert err == strings_es.SALES_INVALID_AMOUNT


def test_payment_status_message():
    msg = sales_controller.payment_status_message("10.00", "", total=3000)
    assert msg == strings_es.SALES_REMAINING.format(remaining="20.00")
    msg = sales_controller.payment_status_message("40.00", "", total=3000)
    assert msg == strings_es.SALES_OVERPAID.format(diff="10.00")
    assert sales_controller.payment_status_message("30.00", "", total=3000) is None
    assert (
        sales_controller.payment_status_message("x", "", total=3000)
        == strings_es.SALES_INVALID_AMOUNT
    )


def test_submit_error_message():
    cart = [_line()]
    items = sales_controller.to_sale_items(cart)
    payments = [SalePaymentInput("cash", 2000)]
    assert sales_controller.submit_error_message([], [], False, None) == strings_es.SALES_EMPTY_CART_ERROR
    credit_msg = sales_controller.submit_error_message(items, [], True, None)
    assert credit_msg == strings_es.SALES_NEED_CUSTOMER_NAME
    assert sales_controller.submit_error_message(items, [], True, "Pepe") is None
    nobody = sales_controller.submit_error_message(items, [], False, None)
    assert nobody == strings_es.SALES_NO_PAYMENT_ERROR
    mismatch = sales_controller.submit_error_message(
        items, [SalePaymentInput("cash", 1000)], False, None
    )
    assert mismatch == strings_es.SALES_PAYMENT_MISMATCH.format(paid="10.00", total="20.00")
    assert sales_controller.submit_error_message(items, payments, False, None) is None


def test_translate_write_error():
    assert (
        sales_controller.translate_write_error(PaymentTotalMismatch("x"))
        == strings_es.SALES_NO_PAYMENT_ERROR
    )
    assert (
        sales_controller.translate_write_error(
            ValueError("A credit sale requires a customer name.")
        )
        == strings_es.SALES_NEED_CUSTOMER_NAME
    )
    assert "x" in sales_controller.translate_write_error(RuntimeError("x"))


def test_format_line_summary():
    summary = sales_controller.format_line_summary(_line(price=1500))
    assert "Azúcar" in summary and "15.00" in summary


def test_format_methods_label():
    assert (
        sales_controller.format_methods_label(
            [{"method": "cash", "amount": 100}], False, None
        )
        == strings_es.BALANCE_CASH_LABEL
    )
    assert (
        sales_controller.format_methods_label(
            [{"method": "cash", "amount": 1}, {"method": "qr", "amount": 1}],
            False,
            None,
        )
        == f"{strings_es.BALANCE_CASH_LABEL} + {strings_es.BALANCE_QR_LABEL}"
    )
    assert sales_controller.format_methods_label([], True, "Pepe") == strings_es.SALES_METHODS_CREDIT.format(
        customer="Pepe"
    )
