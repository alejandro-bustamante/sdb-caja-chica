"""Pure controller logic for the sales screen — no Flet imports.

Everything that decides *what* to show or *whether* an action is valid
(cart math, payment checks, message selection) lives here so it can be unit
tested without booting Flet (plan Task 1 §2, Task 8).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.balance import format_cents
from app.domain.types import SaleItemInput, SalePaymentInput
from app.domain.validation import (
    CreditSaleWithPayments,
    NonCreditSaleWithoutPayments,
    PaymentTotalMismatch,
    ValidationError,
    validate_sale_payments,
)
from app.ui import strings_es
from app.ui.views.common_controller import parse_money_input, parse_quantity_input


@dataclass
class CartLine:
    product_id: int
    name: str
    quantity: int
    unit_price: int
    overridden: bool = False

    @property
    def total(self) -> int:
        return self.quantity * self.unit_price


def add_cart_line(
    cart: list[CartLine],
    product_id: int,
    name: str,
    quantity: int,
    unit_price: int,
) -> None:
    """Append a line, or merge into an existing line for the same product."""
    for line in cart:
        if line.product_id == product_id:
            line.quantity += quantity
            return
    cart.append(CartLine(product_id=product_id, name=name, quantity=quantity, unit_price=unit_price))


def remove_cart_line(cart: list[CartLine], index: int) -> None:
    del cart[index]


def override_cart_line_price(cart: list[CartLine], index: int, new_price: int) -> None:
    """Set a line's unit price and mark it as manually overridden."""
    cart[index].unit_price = new_price
    cart[index].overridden = True


def cart_total(cart: Sequence[CartLine]) -> int:
    return sum(line.total for line in cart)


def to_sale_items(cart: Sequence[CartLine]) -> list[SaleItemInput]:
    return [
        SaleItemInput(
            product_id=line.product_id,
            quantity=line.quantity,
            unit_price_applied=line.unit_price,
            price_manually_overridden=line.overridden,
        )
        for line in cart
    ]


def add_line_input_error(
    product_id: int | None, quantity_text: str | None
) -> str | None:
    """Validate the "add to cart" inputs; returns a Spanish message or None."""
    if product_id is None:
        return strings_es.SALES_NEED_PRODUCT
    if parse_quantity_input(quantity_text) is None:
        return strings_es.SALES_INVALID_QUANTITY
    return None


def build_payments_from_texts(
    cash_text: str | None, qr_text: str | None
) -> tuple[list[SalePaymentInput] | None, str | None]:
    """Parse payment fields into rows. ``(None, message)`` on invalid input."""
    cash = parse_money_input(cash_text)
    qr = parse_money_input(qr_text)
    if (cash_text or "").strip() and cash is None:
        return None, strings_es.SALES_INVALID_AMOUNT
    if (qr_text or "").strip() and qr is None:
        return None, strings_es.SALES_INVALID_AMOUNT
    payments: list[SalePaymentInput] = []
    if cash:
        payments.append(SalePaymentInput(method="cash", amount=cash))
    if qr:
        payments.append(SalePaymentInput(method="qr", amount=qr))
    return payments, None


def payment_status_message(
    cash_text: str | None, qr_text: str | None, total: int
) -> str | None:
    """Live helper text under the payment fields (""/None when all good)."""
    cash = parse_money_input(cash_text)
    qr = parse_money_input(qr_text)
    if (cash_text or "").strip() and cash is None:
        return strings_es.SALES_INVALID_AMOUNT
    if (qr_text or "").strip() and qr is None:
        return strings_es.SALES_INVALID_AMOUNT
    paid = (cash or 0) + (qr or 0)
    if paid < total:
        return strings_es.SALES_REMAINING.format(remaining=format_cents(total - paid))
    if paid > total:
        return strings_es.SALES_OVERPAID.format(diff=format_cents(paid - total))
    return None


def submit_error_message(
    items: Sequence[SaleItemInput],
    payments: Sequence[SalePaymentInput],
    is_credit: bool,
    customer_name: str | None,
) -> str | None:
    """Full client-side validation for the submit; returns message or None."""
    if not items:
        return strings_es.SALES_EMPTY_CART_ERROR
    if is_credit and not (customer_name or "").strip():
        return strings_es.SALES_NEED_CUSTOMER_NAME
    try:
        validate_sale_payments(items, payments, is_credit)
    except PaymentTotalMismatch:
        return strings_es.SALES_PAYMENT_MISMATCH.format(
            paid=format_cents(sum(p.amount for p in payments)),
            total=format_cents(sum(i.total for i in items)),
        )
    except NonCreditSaleWithoutPayments:
        return strings_es.SALES_NO_PAYMENT_ERROR
    except CreditSaleWithPayments:
        return strings_es.SALES_NO_PAYMENT_ERROR
    return None


def translate_write_error(exc: Exception) -> str:
    """Map repository/validation exceptions to a Spanish message."""
    if isinstance(exc, PaymentTotalMismatch):
        return strings_es.SALES_NO_PAYMENT_ERROR
    if isinstance(exc, (NonCreditSaleWithoutPayments, CreditSaleWithPayments)):
        return strings_es.SALES_NO_PAYMENT_ERROR
    if isinstance(exc, ValidationError):
        return strings_es.SALES_CANNOT_EDIT_COLLECTED
    if isinstance(exc, ValueError) and "requires a customer name" in str(exc):
        return strings_es.SALES_NEED_CUSTOMER_NAME
    return strings_es.SALES_WRITE_ERROR.format(message=str(exc))


def format_line_summary(line: CartLine) -> str:
    """One cart line's single-line summary: ``x2 @ $ 20.00 = $ 40.00``."""
    return (
        f"{line.name}  x{line.quantity} @ $ {format_cents(line.unit_price)}"
        f"  = $ {format_cents(line.total)}"
    )


def format_methods_label(
    payments: Sequence[dict],
    is_credit: bool,
    customer_name: str | None,
) -> str:
    """Payment split label: ``Efectivo + QR`` or ``Fiado (Pepe)``."""
    if is_credit:
        return strings_es.SALES_METHODS_CREDIT.format(customer=customer_name or "?")
    methods = [strings_es.BALANCE_CASH_LABEL] * any(
        p["method"] == "cash" for p in payments
    ) + [strings_es.BALANCE_QR_LABEL] * any(p["method"] == "qr" for p in payments)
    if not methods:
        return ""
    return " + ".join(methods)


def cart_line_error(cart: Sequence[CartLine]) -> str | None:
    """Validation before building sale items, e.g. submit with empty cart."""
    if not cart:
        return strings_es.SALES_EMPTY_CART_ERROR
    return None
