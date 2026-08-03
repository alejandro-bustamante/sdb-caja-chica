"""Tests for repositories.products + product_prices append-only invariant."""

from __future__ import annotations

from app.db.repositories import products


def test_create_and_list_current_price(conn, user_id):
    pid = products.create_product(conn, "Cloro", 1500, user_id)
    listed = {p.id: p for p in products.list_active_products(conn)}
    assert listed[pid].current_price == 1500


def test_update_price_supersedes_and_preserves_old(conn, user_id):
    pid = products.create_product(conn, "Cloro", 1500, user_id)
    new_id = products.update_product_price(conn, pid, 1800, user_id, reason="rise")

    assert {p.id: p.current_price for p in products.list_active_products(conn)}[pid] == 1800

    rows = conn.execute(
        "SELECT price, superseded_at FROM product_prices WHERE product_id = ?"
        " ORDER BY id",
        (pid,),
    ).fetchall()
    # Old price never mutated; only marked superseded. New row inserted.
    assert [r["price"] for r in rows] == [1500, 1800]
    assert rows[0]["superseded_at"] is not None
    assert rows[1]["superseded_at"] is None
    assert new_id is not None


def test_set_product_active_toggles(conn, user_id):
    pid = products.create_product(conn, "Cloro", 1500, user_id)
    products.set_product_active(conn, pid, False, user_id)
    assert products.list_active_products(conn) == []
    product = conn.execute("SELECT active FROM products WHERE id = ?", (pid,)).fetchone()
    assert product["active"] == 0
