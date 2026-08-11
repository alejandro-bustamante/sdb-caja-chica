"""Tests for repositories.expenses (versioning + soft delete + payments)."""

from __future__ import annotations

from app.db.repositories import expenses
from app.domain.balance import compute_available_cash, compute_available_qr
from app.domain.types import ExpensePaymentInput


def test_create_and_edit_expense(conn, user_id):
    eid = expenses.create_expense(
        conn, "Luz", [ExpensePaymentInput("cash", 5000)], user_id
    )
    logical = expenses.get_current_expense(conn, 1)
    assert logical is not None and logical["id"] == eid and logical["amount"] == 5000

    expenses.edit_expense(
        conn, 1, "Luz enero", [ExpensePaymentInput("cash", 4800)], user_id
    )
    current = expenses.get_current_expense(conn, 1)
    assert current["amount"] == 4800
    history = conn.execute(
        "SELECT version, amount, superseded_at FROM expenses"
        " WHERE logical_id = 1 ORDER BY version"
    ).fetchall()
    assert [r["version"] for r in history] == [1, 2]
    # Old version preserved & unchanged, only superseded_at set.
    assert history[0]["amount"] == 5000
    assert history[0]["superseded_at"] is not None
    assert compute_available_cash(conn) == -4800


def test_edit_preserves_payment_snapshots_per_version(conn, user_id):
    expenses.create_expense(
        conn,
        "Luz",
        [ExpensePaymentInput("cash", 2000), ExpensePaymentInput("qr", 1000)],
        user_id,
    )
    expenses.edit_expense(conn, 1, "Luz", [ExpensePaymentInput("qr", 4000)], user_id)
    v1 = conn.execute(
        "SELECT e.id FROM expenses e WHERE e.logical_id = 1 AND e.version = 1"
    ).fetchone()["id"]
    v2 = conn.execute(
        "SELECT e.id FROM expenses e WHERE e.logical_id = 1 AND e.version = 2"
    ).fetchone()["id"]
    v1_pay = {p["method"]: p["amount"] for p in expenses.get_expense_payments(conn, v1)}
    v2_pay = {p["method"]: p["amount"] for p in expenses.get_expense_payments(conn, v2)}
    assert v1_pay == {"cash": 2000, "qr": 1000}
    assert v2_pay == {"qr": 4000}
    assert compute_available_cash(conn) == 0
    assert compute_available_qr(conn) == -4000


def test_void_expense_soft_deletes(conn, user_id):
    expenses.create_expense(
        conn, "Luz", [ExpensePaymentInput("cash", 5000)], user_id
    )
    expenses.void_expense(conn, 1, user_id)
    current = expenses.get_current_expense(conn, 1)
    assert current["deleted_at"] is not None
    # Voided expense no longer counts against available cash.
    assert compute_available_cash(conn) == 0
    # Original row still present.
    assert conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE logical_id = 1 AND version = 1"
    ).fetchone()[0] == 1
