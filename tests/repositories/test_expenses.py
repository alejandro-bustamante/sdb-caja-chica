"""Tests for repositories.expenses (versioning + soft delete)."""

from __future__ import annotations

from app.db.repositories import expenses
from app.domain.balance import compute_available_cash


def test_create_and_edit_expense(conn, user_id):
    eid = expenses.create_expense(conn, "Luz", 5000, user_id)
    logical = expenses.get_current_expense(conn, 1)
    assert logical is not None and logical["id"] == eid and logical["amount"] == 5000

    expenses.edit_expense(conn, 1, "Luz enero", 4800, user_id)
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


def test_void_expense_soft_deletes(conn, user_id):
    expenses.create_expense(conn, "Luz", 5000, user_id)
    expenses.void_expense(conn, 1, user_id)
    current = expenses.get_current_expense(conn, 1)
    assert current["deleted_at"] is not None
    # Voided expense no longer counts against available cash.
    assert compute_available_cash(conn) == 0
    # Original row still present.
    assert conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE logical_id = 1 AND version = 1"
    ).fetchone()[0] == 1
