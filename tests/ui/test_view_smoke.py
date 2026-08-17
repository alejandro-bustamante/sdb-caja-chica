"""One build-smoke test per view (plan Task 8 §2): construct each view's root
control against a fresh migrated DB with a fake session, without a real Page.
"""

from __future__ import annotations

import flet as ft
import pytest

from app.db.repositories import (
    batches as batches_repo,
)
from app.db.repositories import (
    cash_counts as cash_counts_repo,
)
from app.db.repositories import (
    debts as debts_repo,
)
from app.db.repositories import (
    expenses as expenses_repo,
)
from app.db.repositories import (
    products as products_repo,
)
from app.db.repositories import (
    sales as sales_repo,
)
from app.domain.types import ExpensePaymentInput, SaleItemInput, SalePaymentInput
from app.ui.session import Session
from app.ui.views import (
    audit as audit_view,
)
from app.ui.views import (
    cash_counts as cash_counts_view,
)
from app.ui.views import (
    catalog as catalog_view,
)
from app.ui.views import (
    debts as debts_view,
)
from app.ui.views import (
    expenses as expenses_view,
)
from app.ui.views import (
    export as export_view,
)
from app.ui.views import (
    restock as restock_view,
)
from app.ui.views import (
    sales as sales_view,
)

VIEW_BUILDERS = [
    sales_view.build,
    catalog_view.build,
    restock_view.build,
    expenses_view.build,
    debts_view.build,
    cash_counts_view.build,
    export_view.build,
    audit_view.build,
]

VIEW_NAMES = [b.__module__.rsplit(".", 1)[-1] for b in VIEW_BUILDERS]


@pytest.mark.parametrize("builder", VIEW_BUILDERS, ids=VIEW_NAMES)
def test_each_view_builds_without_page(builder, conn, user_id):
    session = Session(user_id=user_id, user_name="Alice")
    calls: list = []
    root = builder(conn, session, lambda: calls.append(1))
    assert isinstance(root, ft.Control)
    assert calls == []


def _seed_data(conn, user_id):
    pid = products_repo.create_product(conn, "Azúcar", 1000, user_id)
    batches_repo.create_batch(
        conn, [(pid, 10)], [ExpensePaymentInput("cash", 5000)], "flete", user_id
    )
    cid = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1000)],
        [SalePaymentInput("cash", 2000)],
        False,
        None,
        None,
        user_id,
    )
    sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1000)],
        [],
        True,
        "Pepe",
        "a cuaderno",
        user_id,
    )
    debts_repo.record_partial_payment(conn, 1, 400, user_id)
    expenses_repo.create_expense(
        conn, "Luz", [ExpensePaymentInput("cash", 3000)], user_id
    )
    cash_counts_repo.record_cash_count(conn, counted_cash=500, user_id=user_id)
    return pid, cid


def test_views_build_with_realistic_data(conn, user_id):
    """Views must build fine with populated data (lists filled, no exceptions)."""
    session = Session(user_id=user_id, user_name="Alice")
    _seed_data(conn, user_id)
    for builder in VIEW_BUILDERS:
        root = builder(conn, session, lambda: None)
        assert isinstance(root, ft.Control)


def test_shell_builds_with_realistic_data(conn, user_id):
    from app.ui.shell import build_shell

    session = Session(user_id=user_id, user_name="Alice")
    _seed_data(conn, user_id)

    class StubPage:
        def update(self):
            pass

        def show_dialog(self, dialog):
            pass

        def pop_dialog(self, dialog=None):
            pass

    root = build_shell(StubPage(), conn, session)
    assert isinstance(root, ft.Control)
