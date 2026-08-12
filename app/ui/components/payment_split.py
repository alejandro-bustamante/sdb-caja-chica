"""Shared cash/QR payment-split widget, mounted by the sales, expenses and
restock screens (plan-03 Task 2).

The three screens all need "one or two amounts across cash/QR". This widget
owns both amount fields plus the live "remaining" hint single time — instead
of a third copy-paste — but stays a thin wire: the authoritative sum check
remains server-side in ``validate_sale_payments`` / ``validate_expense_payments``,
and the pure hint arithmetic lives in ``common_controller.payment_split_status``
(unit-tested once, reused by all three screens' controllers).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.ui.views.common_controller import parse_money_input


class PaymentSplit:
    """Two amount fields (cash, QR) with a live status hint.

    ``message_builder(cash_text, qr_text) -> str | None`` produces the hint on
    every field change (the shared ``payment_split_status`` helper, or a
    screen-specific wrapper in its controller). Use ``cash_text`` / ``qr_text``
    to read the raw input and ``clear`` / ``set_values`` in edit flows.
    """

    def __init__(
        self,
        *,
        cash_label: str,
        qr_label: str,
        message_builder: Callable[[str | None, str | None], str | None],
        field_width: int = 170,
        visible: bool = True,
    ) -> None:
        self._message_builder = message_builder
        self.cash_field = ft.TextField(
            label=cash_label,
            keyboard_type=ft.KeyboardType.NUMBER,
            width=field_width,
        )
        self.qr_field = ft.TextField(
            label=qr_label,
            keyboard_type=ft.KeyboardType.NUMBER,
            width=field_width,
        )
        self.hint = ft.Text("", color=ft.Colors.AMBER_700)
        self.cash_field.on_change = lambda e: self.update_hint()
        self.qr_field.on_change = lambda e: self.update_hint()
        self.control = ft.Row(
            [self.cash_field, self.qr_field, self.hint], spacing=12
        )
        self.control.visible = visible

    @property
    def cash_text(self) -> str | None:
        return self.cash_field.value

    @property
    def qr_text(self) -> str | None:
        return self.qr_field.value

    def update_hint(self) -> None:
        """Recompute the live status hint from the current field values."""
        self.hint.value = self._message_builder(self.cash_text, self.qr_text) or ""

    def clear(self) -> None:
        """Empty both fields and reset the hint."""
        self.cash_field.value = ""
        self.qr_field.value = ""
        self.hint.value = ""

    def set_values(self, cash_cents: int | None, qr_cents: int | None) -> None:
        """Populate both fields (in cents) for an edit-reopen flow."""
        self.cash_field.value = None if cash_cents is None else _cents_text(cash_cents)
        self.qr_field.value = None if qr_cents is None else _cents_text(qr_cents)
        self.update_hint()

    def parsed_cents(self) -> tuple[int | None, int | None]:
        """The fields' parsed integer-cents values (``None`` if empty/invalid)."""
        return parse_money_input(self.cash_text), parse_money_input(self.qr_text)


def _cents_text(cents: int) -> str:
    from app.domain.balance import format_cents

    return format_cents(cents)
