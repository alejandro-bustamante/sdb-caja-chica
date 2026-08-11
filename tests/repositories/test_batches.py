"""Tests for repositories.batches and its stock/expense effects."""

from __future__ import annotations

from app.db.repositories import batches
from app.db.repositories.expenses import get_current_expense, get_expense_payments
from app.db.repositories.products import create_product
from app.domain.balance import compute_available_cash, compute_available_qr, compute_current_stock
from app.domain.types import ExpensePaymentInput


def _setup_product(conn, user_id: int, name: str = "Azúcar", price: int = 1000) -> int:
    return create_product(conn, name, price, user_id)


def test_create_batch_moves_stock_and_links_expense(conn, user_id):
    pid = _setup_product(conn, user_id)
    qid = _setup_product(conn, user_id, name="Sal", price=500)
    batch_id = batches.create_batch(
        conn,
        [(pid, 10), (qid, 5)],
        [ExpensePaymentInput("cash", 15000)],
        "Repo",
        user_id,
    )
    assert batch_id is not None
    assert compute_current_stock(conn, pid) == 10
    assert compute_current_stock(conn, qid) == 5

    exp = get_current_expense(conn, 1)
    assert exp is not None and exp["amount"] == 15000
    assert compute_available_cash(conn) == -15000


def test_create_batch_expense_can_pay_by_qr(conn, user_id):
    pid = _setup_product(conn, user_id)
    batches.create_batch(
        conn,
        [(pid, 4)],
        [ExpensePaymentInput("cash", 2000), ExpensePaymentInput("qr", 3000)],
        "Repo",
        user_id,
    )
    exp = get_current_expense(conn, 1)
    assert exp is not None and exp["amount"] == 5000
    payments = get_expense_payments(conn, int(exp["id"]))
    assert {p["method"]: p["amount"] for p in payments} == {"cash": 2000, "qr": 3000}
    assert compute_available_cash(conn) == -2000
    assert compute_available_qr(conn) == -3000


def test_create_batch_writes_expected_row_counts(conn, user_id):
    """Exit criterion (plan Task 4): one batch, N items, N stock movements,
    and exactly one linked expense (version 1), all in a single transaction."""
    pid = _setup_product(conn, user_id)
    qid = _setup_product(conn, user_id, name="Sal", price=500)
    batches.create_batch(
        conn,
        [(pid, 4), (qid, 2)],
        [ExpensePaymentInput("cash", 6000)],
        "Repo",
        user_id,
    )
    assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM batch_items").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] == 2
    expenses_rows = conn.execute(
        "SELECT version, amount, superseded_at, deleted_at FROM expenses"
    ).fetchall()
    assert len(expenses_rows) == 1
    assert expenses_rows[0]["version"] == 1
    assert expenses_rows[0]["amount"] == 6000
    assert expenses_rows[0]["superseded_at"] is None
    assert expenses_rows[0]["deleted_at"] is None


def test_create_batch_without_expense(conn, user_id):
    pid = _setup_product(conn, user_id)
    batches.create_batch(
        conn,
        [(pid, 3)],
        None,
        None,
        user_id,
    )
    assert compute_current_stock(conn, pid) == 3
    assert compute_available_cash(conn) == 0


def test_batch_expense_reference_follows_the_expense(conn, user_id):
    from app.db.repositories.expenses import edit_expense, void_expense

    pid = _setup_product(conn, user_id)
    batches.create_batch(
        conn,
        [(pid, 3)],
        [ExpensePaymentInput("cash", 15000)],
        "Repo",
        user_id,
    )
    first = batches.resolve_batch_expense(conn, 1)
    assert first is not None and first["amount"] == 15000

    edit_expense(conn, 1, "Repo ed", [ExpensePaymentInput("cash", 12000)], user_id)
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
        [ExpensePaymentInput("cash", 15000)],
        "Repo",
        user_id,
    )
    assert batches.is_batch_expense_deleted(conn, 1) is False
    void_expense(conn, 1, user_id)
    assert batches.is_batch_expense_deleted(conn, 1) is True
