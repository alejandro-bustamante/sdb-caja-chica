"""Tests for the normalized audit event query (plan-05 Task 1 exit criteria).

An audit tool that silently drops or misattributes events is worse than no
audit tool, so these tests cover each of the six categories and each of the
three change types independently, combined filters, the "todo" time option,
and pagination against ``count_audit_events``.
"""

from __future__ import annotations

import time

import pytest

from app.db.repositories import batches as batches_repo
from app.db.repositories import cash_counts as cash_counts_repo
from app.db.repositories import debts as debts_repo
from app.db.repositories import expenses as expenses_repo
from app.db.repositories import products as products_repo
from app.db.repositories import sales as sales_repo
from app.domain import audit
from app.domain.types import ExpensePaymentInput, SaleItemInput, SalePaymentInput


def _seed_full_mix(conn, user_id):
    """One event in every category (plus a couple of edits/voids)."""
    pid = products_repo.create_product(conn, "Coca-Cola 600ml", 1500, user_id)
    products_repo.update_product_price(conn, pid, 1800, user_id, reason="sube precio")
    batches_repo.create_batch(
        conn, [(pid, 10)], [ExpensePaymentInput("cash", 5000)], "flete", user_id
    )
    cash_sale_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1500)],
        [SalePaymentInput("cash", 2000), SalePaymentInput("qr", 1000)],
        False,
        None,
        None,
        user_id,
    )
    credit_sale_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1500)],
        [],
        True,
        "María Pérez",
        "a cuaderno",
        user_id,
    )
    debts_repo.record_partial_payment(conn, credit_sale_id, 500, user_id)
    expense_id = expenses_repo.create_expense(
        conn, "Alquiler local", [ExpensePaymentInput("cash", 3000)], user_id
    )
    cash_counts_repo.record_cash_count(
        conn, counted_cash=1000, user_id=user_id, note="diario"
    )
    return pid, cash_sale_id, credit_sale_id, expense_id


def test_each_category_queried_independently(conn, user_id):
    _seed_full_mix(conn, user_id)
    for category in audit.ALL_CATEGORIES:
        events = audit.list_audit_events(conn, categories=(category,))
        assert events, f"category {category} should have at least one event"
        assert {e.category for e in events} == {category}


def test_change_types_independently(conn, user_id):
    pid, cash_sale_id, _, expense_id = _seed_full_mix(conn, user_id)
    # An edit of the cash sale -> version 2 (edicion); a voided expense ->
    # eliminacion; the rest are registros.
    sales_repo.edit_sale(
        conn,
        cash_sale_id,
        [SaleItemInput(product_id=pid, quantity=3, unit_price_applied=1500)],
        [SalePaymentInput("cash", 4500)],
        False,
        None,
        None,
        user_id,
    )
    expenses_repo.void_expense(conn, expense_id, user_id)

    for change_type in audit.ALL_CHANGE_TYPES:
        events = audit.list_audit_events(conn, change_types=(change_type,))
        assert events, f"change type {change_type} should have at least one event"
        assert {e.change_type for e in events} == {change_type}

    # Eliminación is only reachable for ventas and gastos (plan-05 Task 1.1).
    eliminated = audit.list_audit_events(conn, change_types=(audit.CHANGE_ELIMINACION,))
    assert {e.category for e in eliminated} <= {audit.CATEGORY_SALES, audit.CATEGORY_EXPENSES}


def test_combined_filters(conn, user_id, other_user_id):
    _seed_full_mix(conn, user_id)
    sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=1, quantity=1, unit_price_applied=500)],
        [SalePaymentInput("cash", 500)],
        False,
        None,
        None,
        other_user_id,
    )
    events = audit.list_audit_events(
        conn,
        user_id=user_id,
        categories=(audit.CATEGORY_SALES,),
        change_types=(audit.CHANGE_REGISTRO,),
    )
    assert events
    assert {e.category for e in events} == {audit.CATEGORY_SALES}
    assert {e.change_type for e in events} == {audit.CHANGE_REGISTRO}
    assert {e.user_id for e in events} == {user_id}

    # Same filters, counting path — must agree with the list path.
    assert audit.count_audit_events(
        conn,
        user_id=user_id,
        categories=(audit.CATEGORY_SALES,),
        change_types=(audit.CHANGE_REGISTRO,),
    ) == len(events)


def test_todo_time_option_includes_old_events(conn, user_id):
    """'Todo' must not silently cap history — a backdated event only shows up
    when no lower bound is applied."""
    pid = products_repo.create_product(conn, "Harina", 1000, user_id)
    credit_sale_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1000)],
        [],
        True,
        "Vieja deuda",
        None,
        user_id,
    )
    old_ts = int(time.time()) - 400 * 86400  # over a year ago
    conn.execute(
        "INSERT INTO debt_payments (sale_id, amount, timestamp, user_id)"
        " VALUES (?, ?, ?, ?)",
        (credit_sale_id, 999, old_ts, user_id),
    )

    since_30d = audit.preset_since("30d")
    assert since_30d is not None
    # Recent events: the sale and the product's creation (both today). The
    # backdated debt payment is excluded once a lower bound is applied.
    assert audit.count_audit_events(conn, since=since_30d) == 2
    assert audit.count_audit_events(conn, since=None) == 3  # + old payment
    old_events = audit.list_audit_events(conn, since=None)
    assert any(e.amount == 999 and e.category == audit.CATEGORY_DEBTS for e in old_events)


def test_pagination_matches_count(conn, user_id):
    for cents in range(100, 800, 100):  # 7 cash counts, distinct amounts
        cash_counts_repo.record_cash_count(conn, counted_cash=cents, user_id=user_id)
    total = audit.count_audit_events(conn)
    assert total == 7

    full = audit.list_audit_events(conn, limit=50, offset=0)
    assert len(full) == total

    pages: list[audit.AuditEvent] = []
    for offset in (0, 3, 6):
        pages.extend(audit.list_audit_events(conn, limit=3, offset=offset))
    assert len(pages) == total
    # No duplicates across page boundaries, and the same set as a full fetch.
    assert {(e.timestamp, e.amount) for e in pages} == {(e.timestamp, e.amount) for e in full}

    # Pagination is newest-first.
    timestamps = [e.timestamp for e in full]
    assert timestamps == sorted(timestamps, reverse=True)


def test_deactivate_reactivate_product_produces_zero_events(conn, user_id):
    """Known limitation (plan-05 Task 1.3): products.active is a plain mutable
    flag, so toggling it is invisible to the audit trail. The product's
    creation still counts; the toggles themselves must add nothing."""
    pid = products_repo.create_product(conn, "Azúcar", 1000, user_id)
    before = audit.count_audit_events(conn, categories=(audit.CATEGORY_CATALOG,))
    assert before == 1
    products_repo.set_product_active(conn, pid, False, user_id)
    products_repo.set_product_active(conn, pid, True, user_id)
    after = audit.count_audit_events(conn, categories=(audit.CATEGORY_CATALOG,))
    assert after == before  # zero new events from the toggles


def test_event_payloads_for_summaries(conn, user_id):
    pid, cash_sale_id, credit_sale_id, expense_id = _seed_full_mix(conn, user_id)

    cash_sale_event = next(
        e
        for e in audit.list_audit_events(conn, categories=(audit.CATEGORY_SALES,))
        if e.entity_logical_id == cash_sale_id
    )
    assert cash_sale_event.is_credit is False
    assert cash_sale_event.amount == 3000  # 2 x $15.00
    assert cash_sale_event.payment_methods == "cash,qr"
    assert cash_sale_event.change_type == audit.CHANGE_REGISTRO

    credit_sale_event = next(
        e
        for e in audit.list_audit_events(conn, categories=(audit.CATEGORY_SALES,))
        if e.entity_logical_id == credit_sale_id
    )
    assert credit_sale_event.is_credit is True
    assert credit_sale_event.customer_name == "María Pérez"

    debt_event = next(
        e
        for e in audit.list_audit_events(conn, categories=(audit.CATEGORY_DEBTS,))
    )
    assert debt_event.amount == 500
    assert debt_event.customer_name == "María Pérez"
    assert debt_event.entity_logical_id == credit_sale_id

    restock_event = next(
        e
        for e in audit.list_audit_events(conn, categories=(audit.CATEGORY_RESTOCK,))
    )
    assert "Coca-Cola 600ml x10" in restock_event.items_summary
    assert restock_event.entity_logical_id is None

    price_event = next(
        e
        for e in audit.list_audit_events(conn, categories=(audit.CATEGORY_CATALOG,))
        if e.change_type == audit.CHANGE_EDICION
    )
    assert price_event.product_name == "Coca-Cola 600ml"
    assert price_event.previous_price == 1500
    assert price_event.price == 1800
    assert price_event.entity_logical_id == pid

    expense_event = next(
        e
        for e in audit.list_audit_events(conn, categories=(audit.CATEGORY_EXPENSES,))
        if e.entity_logical_id == expense_id
    )
    assert expense_event.description == "Alquiler local"
    assert expense_event.amount == 3000

    arqueo_event = next(
        e
        for e in audit.list_audit_events(conn, categories=(audit.CATEGORY_CASH_COUNTS,))
    )
    assert arqueo_event.amount == 1000
    assert arqueo_event.expected_cash is not None
    assert arqueo_event.difference is not None
    assert arqueo_event.note == "diario"


def test_user_filter_includes_inactive_users(conn, user_id, other_user_id):
    _seed_full_mix(conn, user_id)
    sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=1, quantity=1, unit_price_applied=500)],
        [SalePaymentInput("cash", 500)],
        False,
        None,
        None,
        other_user_id,
    )
    only_other = audit.list_audit_events(conn, user_id=other_user_id)
    assert only_other
    assert {e.user_id for e in only_other} == {other_user_id}


def test_unknown_category_and_change_type_keys_rejected(conn, user_id):
    with pytest.raises(ValueError):
        audit.list_audit_events(conn, categories=("bogus",))
    with pytest.raises(ValueError):
        audit.count_audit_events(conn, change_types=("bogus",))


def test_preset_since():
    assert audit.preset_since(audit.TIME_PRESET_ALL) is None
    for key, seconds in audit.TIME_PRESET_SECONDS.items():
        since = audit.preset_since(key)
        assert since is not None
        assert abs((int(time.time()) - seconds) - since) < 5
