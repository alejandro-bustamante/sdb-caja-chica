"""Shared lightweight data structures used across domain and repositories.

Money values are integer cents throughout (AGENTS.md / DESIGN.md — never
floats). Quantities are integers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SaleItemInput:
    """One sale line as supplied when creating/editing a sale."""

    product_id: int
    quantity: int
    unit_price_applied: int
    price_manually_overridden: bool = False

    @property
    def total(self) -> int:
        return self.quantity * self.unit_price_applied


@dataclass(frozen=True)
class SalePaymentInput:
    """One payment as supplied when creating/editing a sale."""

    method: str  # 'cash' | 'qr'
    amount: int


@dataclass(frozen=True)
class User:
    id: int
    name: str
    active: bool


@dataclass(frozen=True)
class ProductWithCurrentPrice:
    id: int
    name: str
    active: bool
    current_price: int | None  # cents, or None when the product has no price yet


@dataclass(frozen=True)
class StockMovementInput:
    """A signed stock change to persist for a batch or sale."""

    product_id: int
    quantity_delta: int
    batch_item_id: int | None = None
    sale_item_id: int | None = None
    reason: str | None = None
