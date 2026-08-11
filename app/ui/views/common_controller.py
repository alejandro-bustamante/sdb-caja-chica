"""Shared pure helpers for the view layer: input parsing and timestamp display.

No Flet imports — unit-testable without booting the UI (plan Task 1 §2,
Task 8). Presentational formatting decisions (number text -> cents, unix
timestamp -> readable string) live here so views only wire widgets.
"""

from __future__ import annotations

from datetime import datetime

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


def build_expense_payments(
    cash_text: str | None, qr_text: str | None
) -> tuple[list[ExpensePaymentInput] | None, str | None]:
    """Parse the cash/QR split of an expense; ``(payments, error)``.

    Mirrors the sales payment split: either field may be empty, but at least
    one valid, positive amount is required and malformed text is rejected.
    """
    cash = parse_money_input(cash_text)
    qr = parse_money_input(qr_text)
    if (cash_text or "").strip() and cash is None:
        return None, strings_es.EXPENSES_INVALID_AMOUNT
    if (qr_text or "").strip() and qr is None:
        return None, strings_es.EXPENSES_INVALID_AMOUNT
    payments: list[ExpensePaymentInput] = []
    if cash:
        payments.append(ExpensePaymentInput(method="cash", amount=cash))
    if qr:
        payments.append(ExpensePaymentInput(method="qr", amount=qr))
    if not payments:
        return None, strings_es.EXPENSES_NO_PAYMENT
    return payments, None


def start_of_today_ts() -> int:
    """Unix timestamp for local midnight today, for "ventas de hoy" lists."""
    now = datetime.now()
    return int(datetime(now.year, now.month, now.day).timestamp())
