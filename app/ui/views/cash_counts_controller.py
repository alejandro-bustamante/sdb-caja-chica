"""Pure controller logic for the cash-count (arqueo) screen — no Flet imports."""

from __future__ import annotations

from app.domain.balance import format_cents
from app.ui import strings_es
from app.ui.views.common_controller import parse_money_input


def counted_cash_error(counted_text: str | None) -> str | None:
    """Validate counted-cash input; returns a Spanish message or None."""
    amount = parse_money_input(counted_text)
    if amount is None or amount < 0:
        return strings_es.ARQUEO_INVALID_AMOUNT
    return None


def parse_counted(amount_text: str | None) -> int | None:
    parsed = parse_money_input(amount_text)
    if parsed is None or parsed < 0:
        return None
    return parsed


def result_message(counted: int, expected: int) -> str:
    """The prominent result line shown right after recording a count."""
    if counted == expected:
        return strings_es.ARQUEO_RESULT_MATCH.format(
            counted=format_cents(counted), expected=format_cents(expected)
        )
    if counted > expected:
        return strings_es.ARQUEO_RESULT_OVER.format(
            diff=format_cents(counted - expected),
            counted=format_cents(counted),
            expected=format_cents(expected),
        )
    return strings_es.ARQUEO_RESULT_SHORT.format(
        diff=format_cents(expected - counted),
        counted=format_cents(counted),
        expected=format_cents(expected),
    )
