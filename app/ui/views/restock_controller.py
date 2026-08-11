"""Pure controller logic for the restock screen — no Flet imports."""

from __future__ import annotations

from app.domain.types import ExpensePaymentInput
from app.ui import strings_es
from app.ui.views import common_controller
from app.ui.views.common_controller import parse_quantity_input


def add_line_error(product_id: int | None, quantity_text: str | None) -> str | None:
    """Validate an add-line attempt; returns a Spanish message or None."""
    if product_id is None:
        return strings_es.RESTOCK_NEED_PRODUCT
    if parse_quantity_input(quantity_text) is None:
        return strings_es.RESTOCK_INVALID_QUANTITY
    return None


def _has_any_expense(cash_text: str | None, qr_text: str | None) -> bool:
    return bool((cash_text or "").strip() or (qr_text or "").strip())


def expense_payments_error(
    cash_text: str | None, qr_text: str | None
) -> str | None:
    """Validate the optional batch-expense split; message or None.

    Empty cash and QR fields mean "no linked expense" (allowed); any provided
    value must parse as a valid, positive amount.
    """
    if not _has_any_expense(cash_text, qr_text):
        return None
    _, error = common_controller.build_expense_payments(cash_text, qr_text)
    if error is not None:
        return strings_es.RESTOCK_INVALID_EXPENSE
    return None


def build_expense_payments(
    cash_text: str | None, qr_text: str | None
) -> list[ExpensePaymentInput] | None:
    """The validated batch-expense split; ``[]`` means no linked expense."""
    if not _has_any_expense(cash_text, qr_text):
        return []
    payments, _ = common_controller.build_expense_payments(cash_text, qr_text)
    return payments


def line_summary(product_name: str, quantity: int) -> str:
    """Single-line summary for one batch line: ``"Item x10"``."""
    return f"{product_name} x{quantity}"
