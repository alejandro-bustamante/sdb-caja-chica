"""Tests for the list/read query helpers added for the Plan #2 screens."""

from __future__ import annotations

from app.db.repositories import batches, cash_counts, debts, expenses, products, sales
from app.domain.types import ExpensePaymentInput, SaleItemInput, SalePaymentInput


def _seed_sale(conn, user_id, pid, total=2000, is_credit=False, name=None):
    from app.db.repositories import batches as b
    from app.db.repositories import sales as s

    b.create_batch(conn, [(pid, 10)], None, None, user_id)
    payments = [] if is_credit else [SalePaymentInput("cash", total)]
    sale_id = s.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=total)],
        payments,
        is_credit,
        name,
        None,
        user_id,
    )
    return sale_id


def test_list_current_sales_and_items_with_names(conn, user_id):
    pid = products.create_product(conn, "Azúcar", 1000, user_id)
    sale_id = _seed_sale(conn, user_id, pid)
    rows = sales.list_current_sales(conn)
    assert len(rows) == 1
    assert str(rows[0]["id"]) and rows[0]["is_credit"] == 0

    items = sales.get_sale_items(conn, sale_id)
    assert len(items) == 1
    assert items[0]["product_name"] == "Azúcar"
    assert items[0]["quantity"] == 1

    payments = sales.get_sale_payments(conn, sale_id)
    assert payments[0]["method"] == "cash" and payments[0]["amount"] == 2000


def test_list_current_sales_excludes_superseded_and_voided(conn, user_id):
    pid = products.create_product(conn, "Azúcar", 1000, user_id)
    _seed_sale(conn, user_id, pid, total=1000)
    sales.edit_sale(
        conn,
        1,
        [SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1000)],
        [SalePaymentInput("cash", 2000)],
        False,
        None,
        None,
        user_id,
    )
    sales.void_sale(conn, 1, user_id)
    assert sales.list_current_sales(conn) == []


def test_list_current_sales_since_filter(conn, user_id):
    pid = products.create_product(conn, "Azúcar", 1000, user_id)
    from app.db.repositories import batches as b

    b.create_batch(conn, [(pid, 5)], None, None, user_id)
    sales.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1000)],
        [SalePaymentInput("cash", 1000)],
        False,
        None,
        None,
        user_id,
    )
    # Far-future timestamp -> nothing on/after it.
    assert sales.list_current_sales(conn, since_ts=10**15) == []


def test_list_all_products_includes_inactive(conn, user_id):
    pid = products.create_product(conn, "Cloro", 1500, user_id)
    products.set_product_active(conn, pid, False, user_id)
    assert products.list_active_products(conn) == []
    all_products = products.list_all_products(conn)
    assert len(all_products) == 1
    assert all_products[0].id == pid and all_products[0].active is False


def test_list_recent_batches_and_items(conn, user_id):
    pid = products.create_product(conn, "Sal", 500, user_id)
    batches.create_batch(conn, [(pid, 4)], [ExpensePaymentInput("cash", 2000)], "flete", user_id)
    rows = batches.list_recent_batches(conn)
    assert len(rows) == 1
    assert rows[0]["user_name"] == "Alice"
    items = batches.get_batch_items(conn, int(rows[0]["id"]))
    assert items[0]["product_name"] == "Sal"
    assert items[0]["quantity"] == 4


def test_find_batch_for_expense(conn, user_id):
    pid = products.create_product(conn, "Sal", 500, user_id)
    batches.create_batch(conn, [(pid, 4)], [ExpensePaymentInput("cash", 2000)], "flete", user_id)
    found = batches.find_batch_for_expense(conn, 1)
    assert found is not None and found["id"] is not None
    assert batches.find_batch_for_expense(conn, 999) is None


def test_list_current_expenses_with_user(conn, user_id, other_user_id):
    expenses.create_expense(conn, "Luz", [ExpensePaymentInput("cash", 5000)], user_id)
    expenses.create_expense(conn, "Agua", [ExpensePaymentInput("cash", 1000)], other_user_id)
    expenses.edit_expense(conn, 1, "Luz enero", [ExpensePaymentInput("cash", 4800)], user_id)
    rows = expenses.list_current_expenses(conn)
    assert len(rows) == 2
    by_logical = {int(r["logical_id"]): r for r in rows}
    assert by_logical[1]["amount"] == 4800  # current version only
    assert by_logical[1]["user_name"] == "Alice"
    assert by_logical[2]["user_name"] == "Blanca"


def test_list_current_sales_flags_collected_credit(conn, user_id):
    pid = products.create_product(conn, "Azúcar", 1000, user_id)
    _seed_sale(conn, user_id, pid, total=2000)
    _seed_sale(conn, user_id, pid, total=1500, is_credit=True, name="Pepe")
    debts.record_partial_payment(conn, 2, 400, user_id)
    by_logical = {int(r["logical_id"]): r for r in sales.list_current_sales(conn)}
    assert by_logical[1]["has_collections"] == 0
    assert by_logical[2]["has_collections"] == 1


def test_list_settled_debts(conn, user_id):
    pid = products.create_product(conn, "Azúcar", 1000, user_id)
    _seed_sale(conn, user_id, pid, total=2000, is_credit=True, name="Pepe")
    debts.record_partial_payment(conn, 1, 1000, user_id)
    assert debts.list_settled_debts(conn) == []
    debts.mark_debt_paid(conn, 1, user_id)
    (settled,) = debts.list_settled_debts(conn)
    assert settled.customer_name == "Pepe"
    assert settled.outstanding == 0


def test_list_cash_counts_with_user(conn, user_id):
    cash_counts.record_cash_count(conn, counted_cash=100, user_id=user_id, note="a")
    rows = cash_counts.list_cash_counts(conn)
    assert len(rows) == 1
    assert rows[0]["user_name"] == "Alice"
    assert rows[0]["note"] == "a"
