"""Framework-agnostic validation rules (no Flet / no sqlite imports).

Kept framework-independent so it can be reused from the repository layer,
the UI layer, and any non-UI context (tests, future import tools).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.types import SaleItemInput, SalePaymentInput


class ValidationError(Exception):
    """Base class for expected business-rule failures."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PaymentTotalMismatch(ValidationError):
    """Raised when payments don't cover the sale total for a non-credit sale."""


class CreditSaleWithPayments(ValidationError):
    """Raised when a credit sale carries upfront payments."""


class NonCreditSaleWithoutPayments(ValidationError):
    """Raised when a non-credit sale has no payment rows at all."""


class PartialPaymentTooLarge(ValidationError):
    """Raised when a partial debt payment exceeds the remaining balance."""


def validate_sale_payments(
    items: Sequence[SaleItemInput],
    payments: Sequence[SalePaymentInput],
    is_credit: bool,
) -> None:
    """Validate that a sale's payment breakdown is consistent.

    Rules:
      * credit sales must not carry upfront payments;
      * non-credit sales must have at least one payment;
      * the sum of payments must equal the sale total for non-credit sales.
    """
    total = sum(item.total for item in items)
    paid = sum(payment.amount for payment in payments)

    if is_credit:
        if paid != 0:
            raise CreditSaleWithPayments(
                "A credit sale must not have upfront payments."
            )
        return

    if paid == 0:
        raise NonCreditSaleWithoutPayments(
            "A non-credit sale must have at least one payment."
        )
    if paid != total:
        raise PaymentTotalMismatch(
            f"Payment sum does not match sale total: paid {paid} != total {total}."
        )


def validate_partial_payment(amount: int, remaining_balance: int) -> None:
    """A partial debt payment must be positive and not exceed the balance due."""
    if amount <= 0:
        raise PartialPaymentTooLarge("Partial payment must be a positive amount.")
    if amount > remaining_balance:
        raise PartialPaymentTooLarge(
            f"Amount {amount} exceeds remaining balance {remaining_balance}."
        )
