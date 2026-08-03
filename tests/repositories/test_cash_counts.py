"""Tests for repositories.cash_counts (arqueo snapshots)."""

from __future__ import annotations

from app.db.repositories import cash_counts
from app.db.repositories.batches import create_batch
from app.db.repositories.products import create_product
from app.db.repositories.sales import create_sale
from app.domain.types import SaleItemInput, SalePaymentInput


def test_record_cash_count_snapshots_expected_and_difference(conn, user_id):
    pid = create_product(conn, "Azúcar", 1000, user_id)
    create_batch(conn, [(pid, 5)], None, None, user_id)
    create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1000)],
        [SalePaymentInput("cash", 1000)],
        False,
        None,
        None,
        user_id,
    )
    count_id = cash_counts.record_cash_count(conn, counted_cash=1300, user_id=user_id, note="primer arqueo")
    row = conn.execute("SELECT * FROM cash_counts WHERE id = ?", (count_id,)).fetchone()
    assert row is not None
    assert row["expected_cash"] == 1000
    assert row["counted_cash"] == 1300
    assert row["difference"] == 300


def test_cash_count_snapshot_never_recomputed(conn, user_id):
    record = cash_counts.record_cash_count(conn, counted_cash=500, user_id=user_id)
    # Later cash movements must NOT change a past snapshot's expected/difference.
    pid = create_product(conn, "Azúcar", 1000, user_id)
    create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1000)],
        [SalePaymentInput("cash", 1000)],
        False,
        None,
        None,
        user_id,
    )
    row = conn.execute("SELECT * FROM cash_counts WHERE id = ?", (record,)).fetchone()
    record = row["id"]
    row2 = conn.execute("SELECT * FROM cash_counts WHERE id = ?", (record,)).fetchone()
    assert row2["expected_cash"] == 0 and row2["difference"] == 500
