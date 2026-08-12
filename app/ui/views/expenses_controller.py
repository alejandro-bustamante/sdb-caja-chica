"""Pure controller logic for the expenses screen — no Flet imports."""

from __future__ import annotations

from app.domain.types import ExpensePaymentInput
from app.ui import strings_es
from app.ui.views.common_controller import build_expense_payments


def create_form_error(
    description: str | None, cash_text: str | None, qr_text: str | None
) -> str | None:
    """Validate the create/edit expense form; returns a Spanish message or None."""
    if not (description or "").strip():
        return strings_es.EXPENSES_EMPTY_DESC
    _, error = build_expense_payments(cash_text, qr_text)
    return error


def build_payments(
    cash_text: str | None, qr_text: str | None
) -> list[ExpensePaymentInput] | None:
    """The validated expense payment split (``None`` when input is invalid)."""
    payments, _ = build_expense_payments(cash_text, qr_text)
    return payments


def void_warning(linked_to_batch: bool) -> str:
    """Confirmation-dialog warning for voiding an expense."""
    if linked_to_batch:
        return strings_es.EXPENSES_VOID_BATCH_WARNING
    return strings_es.EXPENSES_VOID_WARNING
