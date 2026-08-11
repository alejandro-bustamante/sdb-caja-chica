"""Pure controller logic for the catalog screen — no Flet imports."""

from __future__ import annotations

from app.ui import strings_es
from app.ui.views.common_controller import parse_money_input


def create_form_error(name: str | None, price_text: str | None) -> str | None:
    """Validate the "new product" form; returns a Spanish message or None."""
    if not (name or "").strip():
        return strings_es.CATALOG_EMPTY_NAME
    price = parse_money_input(price_text)
    if price is None or price < 0:
        return strings_es.CATALOG_INVALID_PRICE
    return None


def update_price_error(price_text: str | None) -> str | None:
    """Validate a new-price input; returns a Spanish message or None."""
    price = parse_money_input(price_text)
    if price is None or price < 0:
        return strings_es.CATALOG_INVALID_PRICE
    return None
