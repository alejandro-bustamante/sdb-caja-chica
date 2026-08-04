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


def test_batch_expense_reference_follows_the_expense(conn, user_id):
    from app.db.repositories.expenses import edit_expense, void_expense

    pid = _setup_product(conn, user_id)
    batches.create_batch(
        conn,
        [(pid, 3)],
        expense_amount=15000,
        expense_description="Repo",
        user_id=user_id,
    )
    first = batches.resolve_batch_expense(conn, 1)
    assert first is not None and first["amount"] == 15000

    edit_expense(conn, 1, "Repo ed", 12000, user_id)
    edited = batches.resolve_batch_expense(conn, 1)
    assert edited is not None and edited["amount"] == 12000

    void_expense(conn, 1, user_id)
    assert batches.resolve_batch_expense(conn, 1) is None


def test_is_batch_expense_deleted_distinguishes_no_link_from_deleted(conn, user_id):
    from app.db.repositories.expenses import void_expense

    pid = _setup_product(conn, user_id)
    batches.create_batch(
        conn,
        [(pid, 3)],
        expense_amount=15000,
        expense_description="Repo",
        user_id=user_id,
    )
    assert batches.is_batch_expense_deleted(conn, 1) is False
    void_expense(conn, 1, user_id)
    assert batches.is_batch_expense_deleted(conn, 1) is True
