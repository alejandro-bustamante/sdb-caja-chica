"""Shared pure helpers for the view layer: input parsing, timestamp display,
and the cash/QR payment-split interaction used by the sales, expenses and
restock screens (plan-03 Task 2).

No Flet imports — unit-testable without booting the UI (plan Task 1 §2,
Task 8). Presentational formatting decisions (number text -> cents, unix
timestamp -> readable string) live here so views only wire widgets.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.domain.balance import format_cents
from app.domain.types import ExpensePaymentInput
from app.ui import strings_es


def parse_money_input(text: str | None) -> int | None:
    """Parse a user-typed money amount into integer cents.

    Accepts "10.5", "10,50", "$12.00", "1200". Returns ``None`` for empty or
    malformed input (negative, letters, more than two decimals).
    """
    s = (text or "").strip().strip("$").replace(",", ".")
    if not s:
        return None
    dollars_part, _, cents_part = s.partition(".")
    if "." in s and not cents_part:
        return None
    if not dollars_part.isdigit():
        return None
    if cents_part and (not cents_part.isdigit() or len(cents_part) > 2):
        return None
    dollars = int(dollars_part)
    cents = int(cents_part.ljust(2, "0")) if cents_part else 0
    return dollars * 100 + cents


def parse_quantity_input(text: str | None) -> int | None:
    """Parse a user-typed whole quantity (> 0) or return ``None`` if invalid."""
    s = (text or "").strip()
    if not s or not s.isdigit():
        return None
    value = int(s)
    if value <= 0:
        return None
    return value


def format_items_summary(items) -> str:
    """Product items (dicts with ``product_name`` and ``quantity``)
    -> ``"ItemA x2, ItemB x1"`` for recent-list rows."""
    return ", ".join(f"{item['product_name']} x{item['quantity']}" for item in items)


def format_timestamp(ts: int) -> str:
    """Local readable timestamp for list rows: ``DD/MM HH:MM``."""
    return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def payment_split_status(
    cash_text: str | None,
    qr_text: str | None,
    *,
    total: int | None = None,
    allow_empty: bool = False,
    invalid_message: str = strings_es.EXPENSES_INVALID_AMOUNT,
    no_payment_message: str = strings_es.EXPENSES_NO_PAYMENT,
) -> str | None:
    """Live hint for a cash/QR payment split; ``None`` when the split is fine.

    This is the single implementation of the "do the two amounts cover the
    total?" arithmetic, shared by the sales (needs a ``total``), expenses
    (any positive split) and restock (empty = no linked expense) screens —
    plan-03 Task 2 exit criteria: the sum/remaining logic is tested once here
    and reused by every screen's controller.

    With ``total`` set (sales-style) the split must reach it exactly, and the
    hint reports how much remains / how much is overpaid. Without a ``total``
    (expenses/restock) only malformed text and emptiness matter.
    """
    cash = parse_money_input(cash_text)
    qr = parse_money_input(qr_text)
    for text, parsed in ((cash_text, cash), (qr_text, qr)):
        if (text or "").strip() and parsed is None:
            return invalid_message
    paid = (cash or 0) + (qr or 0)
    if total is not None:
        if paid < total:
            return strings_es.SALES_REMAINING.format(remaining=format_cents(total - paid))
        if paid > total:
            return strings_es.SALES_OVERPAID.format(diff=format_cents(paid - total))
        return None
    if not allow_empty and paid <= 0:
        return no_payment_message
    return None


def build_payment_split(
    cash_text: str | None,
    qr_text: str | None,
    *,
    factory: Callable[[str, int], object],
    invalid_message: str,
    no_payment_message: str,
) -> tuple[list | None, str | None]:
    """Parse the cash/QR split into typed payment rows; ``(rows, error)``.

    Either field may be empty, but at least one valid, positive amount is
    required and any malformed non-empty text is rejected. The ``factory``
    builds each row's domain type (``SalePaymentInput`` / ``ExpensePaymentInput``)
    so both the sales and expenses controllers share this one parse instead of
    copy-pasting it.
    """
    cash = parse_money_input(cash_text)
    qr = parse_money_input(qr_text)
    if (cash_text or "").strip() and cash is None:
        return None, invalid_message
    if (qr_text or "").strip() and qr is None:
        return None, invalid_message
    payments = []
    if cash:
        payments.append(factory("cash", cash))
    if qr:
        payments.append(factory("qr", qr))
    if not payments:
        return None, no_payment_message
    return payments, None


def build_expense_payments(
    cash_text: str | None, qr_text: str | None
) -> tuple[list[ExpensePaymentInput] | None, str | None]:
    """Parse the cash/QR split of an expense; ``(payments, error)``."""
    return build_payment_split(
        cash_text,
        qr_text,
        factory=lambda method, amount: ExpensePaymentInput(method=method, amount=amount),
        invalid_message=strings_es.EXPENSES_INVALID_AMOUNT,
        no_payment_message=strings_es.EXPENSES_NO_PAYMENT,
    )


def format_payment_breakdown(payments) -> str:
    """Payment-split label with amounts for a list row: ``Efectivo $ X / QR $ Y``."""
    parts = []
    for payment in payments:
        label = (
            strings_es.BALANCE_CASH_LABEL
            if payment["method"] == "cash"
            else strings_es.BALANCE_QR_LABEL
        )
        parts.append(f"{label} $ {format_cents(int(payment['amount']))}")
    return " / ".join(parts)


def start_of_today_ts() -> int:
    """Unix timestamp for local midnight today, for "ventas de hoy" lists."""
    now = datetime.now()
    return int(datetime(now.year, now.month, now.day).timestamp())
