"""Tests for repositories.batches and its stock/expense effects."""

from __future__ import annotations

from app.db.repositories import batches
from app.db.repositories.expenses import get_current_expense
from app.db.repositories.products import create_product
from app.domain.balance import compute_available_cash, compute_current_stock


def _setup_product(conn, user_id: int, name: str = "Azúcar", price: int = 1000) -> int:
    return create_product(conn, name, price, user_id)


def test_create_batch_moves_stock_and_links_expense(conn, user_id):
    pid = _setup_product(conn, user_id)
    qid = _setup_product(conn, user_id, name="Sal", price=500)
    batch_id = batches.create_batch(
        conn,
        [(pid, 10), (qid, 5)],
        expense_amount=15000,
        expense_description="Repo",
        user_id=user_id,
    )
    assert batch_id is not None
    assert compute_current_stock(conn, pid) == 10
    assert compute_current_stock(conn, qid) == 5

    exp = get_current_expense(conn, 1)
    assert exp is not None and exp["amount"] == 15000
    assert compute_available_cash(conn) == -15000


def test_create_batch_without_expense(conn, user_id):
    pid = _setup_product(conn, user_id)
    batches.create_batch(
        conn,
        [(pid, 3)],
        expense_amount=None,
        expense_description=None,
        user_id=user_id,
    )
    assert compute_current_stock(conn, pid) == 3
    assert compute_available_cash(conn) == 0
