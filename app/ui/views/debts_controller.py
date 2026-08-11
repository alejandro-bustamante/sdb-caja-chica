"""Pure controller logic for the debts (fiado) screen — no Flet imports."""

from __future__ import annotations

from app.domain.balance import format_cents
from app.ui import strings_es
from app.ui.views.common_controller import parse_money_input


def abono_error(amount_text: str | None, outstanding: int) -> str | None:
    """Validate a partial-payment input; returns a Spanish message or None."""
    amount = parse_money_input(amount_text)
    if amount is None or amount <= 0:
        return strings_es.DEBTS_INVALID_ABONO
    if amount > outstanding:
        return strings_es.DEBTS_ABONO_TOO_LARGE.format(
            outstanding=format_cents(outstanding)
        )
    return None


def parse_abono_amount(amount_text: str | None) -> int | None:
    return parse_money_input(amount_text)
