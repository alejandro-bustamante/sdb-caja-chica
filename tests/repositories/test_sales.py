"""Tests for repositories.sales: versioning, stock netting, soft delete."""

from __future__ import annotations

import pytest

from app.db.repositories import sales
from app.db.repositories.products import create_product
from app.domain.balance import compute_available_cash, compute_current_stock
from app.domain.types import SaleItemInput, SalePaymentInput
from app.domain.validation import ValidationError


def _items(pid: int, qty: int = 1, price: int = 1000):
    return [SaleItemInput(product_id=pid, quantity=qty, unit_price_applied=price)]


def _cash(amount: int):
    return [SalePaymentInput(method="cash", amount=amount)]


def test_create_sale_decrements_stock_and_moves_cash(conn, user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    create_product(conn, "Cloro", 500, user_id)
    # add stock via batch
    from app.db.repositories import batches
    batches.create_batch(conn, [(pid, 10)], None, None, user_id)

    sales.create_sale(
        conn, _items(pid, qty=2, price=1000), _cash(2000), False, None, None, user_id
    )
    assert compute_current_stock(conn, pid) == 8
    assert compute_available_cash(conn) == 2000


def test_edit_sale_reverses_and_reapplies_stock(conn, user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    from app.db.repositories import batches
    batches.create_batch(conn, [(pid, 10)], None, None, user_id)

    sales.create_sale(
        conn, _items(pid, qty=2, price=1000), _cash(2000), False, None, None, user_id
    )
    logical = sales.get_sale_current(conn, 1)
    assert logical is not None

    new_id = sales.edit_sale(
        conn, logical["logical_id"], _items(pid, qty=4, price=1000), _cash(4000),
        False, None, None, user_id,
    )
    assert new_id is not None
    assert compute_current_stock(conn, pid) == 6
    assert compute_available_cash(conn) == 4000

    history = sales.get_sale_history(conn, logical["logical_id"])
    assert len(history) == 2
    old_row = history[0]
    assert old_row["superseded_at"] is not None
    # Old version preserved and unchanged apart from superseded_at.
    assert old_row["version"] == 1


def test_void_sale_reverses_stock_and_cash(conn, user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    from app.db.repositories import batches
    batches.create_batch(conn, [(pid, 10)], None, None, user_id)

    sales.create_sale(
        conn, _items(pid, qty=3, price=1000), _cash(3000), False, None, None, user_id
    )
    sales.void_sale(conn, 1, user_id)
    assert compute_current_stock(conn, pid) == 10
    assert compute_available_cash(conn) == 0
    current = sales.get_sale_current(conn, 1)
    assert current is None  # soft-deleted


def test_credit_sale_requires_no_payments_but_decrements_stock(conn, user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    from app.db.repositories import batches
    batches.create_batch(conn, [(pid, 5)], None, None, user_id)

    sales.create_sale(
        conn, _items(pid, qty=2, price=1000), [], True, "Pepe", None, user_id
    )
    assert compute_current_stock(conn, pid) == 3
    assert compute_available_cash(conn) == 0


def test_reassign_sale_keeps_money_and_current_user_changes(conn, user_id, other_user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    from app.db.repositories import batches
    batches.create_batch(conn, [(pid, 5)], None, None, user_id)
    sales.create_sale(
        conn, _items(pid, qty=1, price=1000), _cash(1000), False, None, None, user_id
    )
    sales.reassign_sale_user(conn, 1, other_user_id, user_id)
    current = sales.get_sale_current(conn, 1)
    assert current is not None
    assert current["current_user"] == other_user_id
    assert current["registered_by_user"] == user_id  # original preserved
    assert compute_available_cash(conn) == 1000
    assert compute_current_stock(conn, pid) == 4


def test_edit_credit_sale_with_collections_is_rejected(conn, user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    from app.db.repositories import batches
    from app.db.repositories.debts import record_partial_payment

    batches.create_batch(conn, [(pid, 5)], None, None, user_id)
    sales.create_sale(
        conn, _items(pid, qty=2, price=1000), [], True, "Pepe", None, user_id
    )
    record_partial_payment(conn, 1, 400, user_id)

    with pytest.raises(ValidationError):
        sales.edit_sale(
            conn, 1, _items(pid, qty=3, price=1000), [], True, "Pepe", None, user_id
        )
    # Rejected path leaves the write / balance untouched.
    assert compute_available_cash(conn) == 400


def test_void_credit_sale_with_collections_is_rejected(conn, user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    from app.db.repositories import batches
    from app.db.repositories.debts import record_partial_payment

    batches.create_batch(conn, [(pid, 5)], None, None, user_id)
    sales.create_sale(
        conn, _items(pid, qty=2, price=1000), [], True, "Pepe", None, user_id
    )
    record_partial_payment(conn, 1, 400, user_id)

    with pytest.raises(ValidationError):
        sales.void_sale(conn, 1, user_id)

    current = sales.get_sale_current(conn, 1)
    assert current is not None and current["deleted_at"] is None
    assert compute_available_cash(conn) == 400
