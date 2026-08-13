"""Seed a fresh ledger with small, realistic demo data.

Used only by the browser (Pyodide) entry point so the hosted demo has
something to look at on first load: two cashiers, a small catalog, a restock
batch with its linked expense, cash/QR/credit sales, a partial debt payment,
an independent expense, and a cash count.

Everything goes through the regular repositories (AGENTS.md §2, §4, §6), so
the invariants hold exactly as in the desktop app. The seed is idempotent by
design: it only runs when the ledger has no users at all.
"""

from __future__ import annotations

import sqlite3

from app.db.repositories import cash_counts as cash_counts_repo
from app.db.repositories import debts as debts_repo
from app.db.repositories import expenses as expenses_repo
from app.db.repositories import products as products_repo
from app.db.repositories import sales as sales_repo
from app.db.repositories import users as users_repo
from app.db.repositories.batches import create_batch
from app.domain.balance import compute_available_cash
from app.domain.types import ExpensePaymentInput, SaleItemInput, SalePaymentInput


def is_empty(conn: sqlite3.Connection) -> bool:
    """Whether the ledger looks fresh (no users yet)."""
    return not users_repo.list_active_users(conn)


def seed_demo(conn: sqlite3.Connection) -> None:
    """Populate a fresh ledger with demo users, stock, sales, and money rows."""
    ana, carlos = (users_repo.create_user(conn, name) for name in ("Ana", "Carlos"))

    product_names_prices = [
        ("Arroz 1kg", 4_200),
        ("Azúcar 1kg", 4_600),
        ("Agua 1L", 2_000),
        ("Pan", 1_500),
    ]
    arroz, azucar, agua, pan = [
        products_repo.create_product(conn, name, price, ana)
        for name, price in product_names_prices
    ]

    # Restock batch with a linked purchase expense, split cash/QR. The
    # numbers are tuned so cash in (sales + debt collections) stays ahead of
    # cash out (cash expenses), leaving a healthy positive drawer balance.
    create_batch(
        conn,
        items=[(arroz, 10), (azucar, 10), (agua, 15), (pan, 15)],
        expense_payments=[
            ExpensePaymentInput(method="cash", amount=13_000),
            ExpensePaymentInput(method="qr", amount=9_000),
        ],
        expense_description="Compra de mercadería (repaso)",
        user_id=ana,
    )

    # Cash sale: 2×arroz + 3×pan = 12,900.
    sales_repo.create_sale(
        conn,
        items=[
            SaleItemInput(product_id=arroz, quantity=2, unit_price_applied=4_200),
            SaleItemInput(product_id=pan, quantity=3, unit_price_applied=1_500),
        ],
        payments=[SalePaymentInput(method="cash", amount=12_900)],
        is_credit=False,
        customer_name=None,
        customer_note=None,
        user_id=ana,
    )

    # QR sale: 3×agua + 1×pan = 7,500.
    sales_repo.create_sale(
        conn,
        items=[
            SaleItemInput(product_id=agua, quantity=3, unit_price_applied=2_000),
            SaleItemInput(product_id=pan, quantity=1, unit_price_applied=1_500),
        ],
        payments=[SalePaymentInput(method="qr", amount=7_500)],
        is_credit=False,
        customer_name=None,
        customer_note=None,
        user_id=carlos,
    )

    # Credit sale (fiado) for Doña Rosa: 2×azúcar = 9,200, no upfront payment.
    sales_repo.create_sale(
        conn,
        items=[SaleItemInput(product_id=azucar, quantity=2, unit_price_applied=4_600)],
        payments=[],
        is_credit=True,
        customer_name="Doña Rosa",
        customer_note=None,
        user_id=ana,
    )

    credit_logical_id = _only_credit_sale_logical_id(conn)

    # Cash sale: 3×arroz + 3×pan = 17,100.
    sales_repo.create_sale(
        conn,
        items=[
            SaleItemInput(product_id=arroz, quantity=3, unit_price_applied=4_200),
            SaleItemInput(product_id=pan, quantity=3, unit_price_applied=1_500),
        ],
        payments=[SalePaymentInput(method="cash", amount=17_100)],
        is_credit=False,
        customer_name=None,
        customer_note=None,
        user_id=carlos,
    )

    # QR sale: 2×agua + 1×pan = 5,500.
    sales_repo.create_sale(
        conn,
        items=[
            SaleItemInput(product_id=agua, quantity=2, unit_price_applied=2_000),
            SaleItemInput(product_id=pan, quantity=1, unit_price_applied=1_500),
        ],
        payments=[SalePaymentInput(method="qr", amount=5_500)],
        is_credit=False,
        customer_name=None,
        customer_note=None,
        user_id=ana,
    )

    # Partial collection on the credit sale, leaving an open debt for the demo.
    debts_repo.record_partial_payment(conn, credit_logical_id, amount=3_000, user_id=ana)

    # Independent (non batch-linked) expense, split cash/QR.
    expenses_repo.create_expense(
        conn,
        description="Bolsas y vasos",
        payments=[
            ExpensePaymentInput(method="cash", amount=10_000),
            ExpensePaymentInput(method="qr", amount=1_000),
        ],
        user_id=carlos,
    )

    # Cash count snapping to the expected drawer balance so the arqueo
    # shows no discrepancy. cash in 33,000 - cash out 23,000 = Bs 100.00.
    expected_cash = compute_available_cash(conn)
    cash_counts_repo.record_cash_count(
        conn, counted_cash=expected_cash, user_id=ana
    )


def _only_credit_sale_logical_id(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT logical_id FROM sales WHERE is_credit = 1 AND deleted_at IS NULL"
        " ORDER BY id DESC LIMIT 1"
    ).fetchall()
    assert rows, "expected a credit sale to exist"
    return int(rows[0]["logical_id"])
