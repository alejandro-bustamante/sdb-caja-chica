"""Tests for the browser-only demo seeder."""

from __future__ import annotations

from app.db.demo_seed import is_empty, seed_demo
from app.db.repositories import cash_counts, debts, expenses, sales, users


def test_seed_only_runs_on_empty_ledger(conn):
    assert is_empty(conn) is True
    seed_demo(conn)
    assert is_empty(conn) is False


def test_seed_populates_a_realistic_ledger(conn):
    seed_demo(conn)

    assert len(users.list_active_users(conn)) == 2
    assert len(sales.list_current_sales(conn)) == 4

    open_debts = debts.list_open_debts(conn)
    assert len(open_debts) == 1
    assert open_debts[0].total == 9_200
    assert open_debts[0].paid == 3_000
    assert open_debts[0].outstanding == 6_200

    assert len(cash_counts.list_cash_counts(conn)) == 1

    active_expenses = expenses.list_current_expenses(conn)
    assert len(active_expenses) == 2  # batch-linked restock + independent


def test_seed_sale_payments_match_totals(conn):
    seed_demo(conn)
    for row in sales.list_current_sales(conn):
        items = sales.get_sale_items(conn, row["id"])
        payments = sales.get_sale_payments(conn, row["id"])
        total = sum(i["quantity"] * i["unit_price_applied"] for i in items)
        paid = sum(p["amount"] for p in payments)
        if not row["is_credit"]:
            assert paid == total
        else:
            assert paid == 0
