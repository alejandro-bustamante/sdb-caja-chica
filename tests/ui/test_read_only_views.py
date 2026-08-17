"""Read-only view tests (plan-04 Task 3 exit criteria).

With ``session.read_only = True`` every screen must construct without raising
and must not mount any write-triggering control (create/edit/void/mark-paid/
abono/record-cash-count) anywhere in the resulting control tree — absent, not
merely disabled. The same builders in a normal (live) session must keep those
controls, as a sanity check that the tree walker actually sees them.
"""

from __future__ import annotations

import flet as ft
import pytest

from app.db.repositories import batches as batches_repo
from app.db.repositories import cash_counts as cash_counts_repo
from app.db.repositories import debts as debts_repo
from app.db.repositories import expenses as expenses_repo
from app.db.repositories import products as products_repo
from app.db.repositories import sales as sales_repo
from app.domain.types import ExpensePaymentInput, SaleItemInput, SalePaymentInput
from app.ui import strings_es
from app.ui.session import Session
from app.ui.views import cash_counts as cash_counts_view
from app.ui.views import catalog as catalog_view
from app.ui.views import debts as debts_view
from app.ui.views import expenses as expenses_view
from app.ui.views import export as export_view
from app.ui.views import restock as restock_view
from app.ui.views import sales as sales_view

VIEW_BUILDERS = [
    sales_view.build,
    catalog_view.build,
    restock_view.build,
    expenses_view.build,
    debts_view.build,
    cash_counts_view.build,
    export_view.build,
]

VIEW_NAMES = [b.__module__.rsplit(".", 1)[-1] for b in VIEW_BUILDERS]

# Every user-facing label that only exists on a write-triggering control.
WRITE_LABELS = {
    strings_es.SALES_ADD_BUTTON,
    strings_es.SALES_SUBMIT_BUTTON,
    strings_es.SALES_EDIT_BUTTON,
    strings_es.SALES_VOID_BUTTON,
    strings_es.SALES_EDIT_LOCKED_TOOLTIP,
    strings_es.SALES_VOID_LOCKED_TOOLTIP,
    strings_es.CATALOG_CREATE_BUTTON,
    strings_es.CATALOG_CHANGE_PRICE_BUTTON,
    strings_es.CATALOG_DEACTIVATE_TOOLTIP,
    strings_es.CATALOG_REACTIVATE_TOOLTIP,
    strings_es.RESTOCK_ADD_BUTTON,
    strings_es.RESTOCK_SUBMIT_BUTTON,
    strings_es.EXPENSES_CREATE_BUTTON,
    strings_es.EXPENSES_EDIT_BUTTON,
    strings_es.EXPENSES_VOID_BUTTON,
    strings_es.DEBTS_MARK_PAID,
    strings_es.DEBTS_ABONO_LINK,
    strings_es.DEBTS_ABONO_BUTTON,
    strings_es.ARQUEO_RECORD_BUTTON,
}

# One representative write label per screen, used as a sanity check that the
# walker detects write controls in a normal session.
_LIVE_LABEL = {
    sales_view.build: strings_es.SALES_ADD_BUTTON,
    catalog_view.build: strings_es.CATALOG_CREATE_BUTTON,
    restock_view.build: strings_es.RESTOCK_ADD_BUTTON,
    expenses_view.build: strings_es.EXPENSES_CREATE_BUTTON,
    debts_view.build: strings_es.DEBTS_MARK_PAID,
    cash_counts_view.build: strings_es.ARQUEO_RECORD_BUTTON,
    export_view.build: None,  # export has no write controls in either mode
}


def _iter_controls(node):
    """Yield a control and every descendant reachable via the usual flet
    composition attributes (controls/content/actions/title)."""
    if node is None:
        return
    yield node
    for attr in ("controls", "actions", "content", "title", "leading", "trailing"):
        value = getattr(node, attr, None)
        if isinstance(value, ft.Control):
            yield from _iter_controls(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, ft.Control):
                    yield from _iter_controls(item)


def _collect_texts(node) -> set[str]:
    """Every user-visible string in the tree (Text values, button texts,
    tooltips, switch labels) — enough to prove write controls are absent.

    In flet 0.86 a Button's label lives in its ``content`` attribute (a plain
    string, distinct from a Control), so that is collected too; ``content``
    that is a Control or list is skipped here and handled by ``_iter_controls``.
    """
    texts: set[str] = set()
    for control in _iter_controls(node):
        if isinstance(control, ft.Text) and control.value:
            texts.add(str(control.value))
        for attr in ("text", "label", "tooltip", "content"):
            value = getattr(control, attr, None)
            if isinstance(value, str) and value:
                texts.add(value)
    return texts


def _seed_data(conn, user_id):
    pid = products_repo.create_product(conn, "Azúcar", 1000, user_id)
    batches_repo.create_batch(
        conn, [(pid, 10)], [ExpensePaymentInput("cash", 5000)], "flete", user_id
    )
    sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1000)],
        [SalePaymentInput("cash", 2000)],
        False,
        None,
        None,
        user_id,
    )
    credit_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1000)],
        [],
        True,
        "Pepe",
        "a cuaderno",
        user_id,
    )
    debts_repo.record_partial_payment(conn, credit_id, 400, user_id)
    expenses_repo.create_expense(
        conn, "Luz", [ExpensePaymentInput("cash", 3000)], user_id
    )
    cash_counts_repo.record_cash_count(conn, counted_cash=500, user_id=user_id)


@pytest.mark.parametrize("builder", VIEW_BUILDERS, ids=VIEW_NAMES)
def test_read_only_view_omits_every_write_control(builder, conn, user_id):
    _seed_data(conn, user_id)
    session = Session(user_id=user_id, user_name="Alice", read_only=True)
    root = builder(conn, session, lambda: None)
    assert isinstance(root, ft.Control)
    labels = _collect_texts(root)
    assert WRITE_LABELS.isdisjoint(labels), (
        f"{VIEW_NAMES[VIEW_BUILDERS.index(builder)]} still mounts write controls: "
        f"{sorted(WRITE_LABELS & labels)}"
    )


@pytest.mark.parametrize("builder", VIEW_BUILDERS, ids=VIEW_NAMES)
def test_live_view_keeps_write_controls(builder, conn, user_id):
    """Sanity check: in a normal session the walker does see write controls."""
    _seed_data(conn, user_id)
    session = Session(user_id=user_id, user_name="Alice")
    root = builder(conn, session, lambda: None)
    expected = _LIVE_LABEL[builder]
    if expected is not None:
        assert expected in _collect_texts(root)


def test_read_only_views_construct_empty_db(conn, user_id):
    """Read-only builds must also work on an empty archived ledger."""
    session = Session(user_id=user_id, user_name="Alice", read_only=True)
    for builder in VIEW_BUILDERS:
        root = builder(conn, session, lambda: None)
        assert isinstance(root, ft.Control)
        assert WRITE_LABELS.isdisjoint(_collect_texts(root))
