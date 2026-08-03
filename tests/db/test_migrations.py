"""Tests for the migration runner and schema application (Task 1)."""

from __future__ import annotations

from app.db.connection import _list_migration_files, iter_tables, migrate, open_connection

EXPECTED_TABLES = {
    "users",
    "products",
    "product_prices",
    "expenses",
    "batches",
    "batch_items",
    "stock_movements",
    "sales",
    "sale_items",
    "sale_payments",
    "debt_payments",
    "cash_counts",
    "schema_version",
}


def test_migrate_creates_all_tables(tmp_path):
    db_path = tmp_path / "test.db"
    conn = open_connection(db_path)
    conn.close()

    applied = migrate(db_path)

    assert applied  # at least one migration ran
    with open_connection(db_path) as conn:
        assert EXPECTED_TABLES <= iter_tables(conn)
        current = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert current == max(_list_migration_files())[0]


def test_migrate_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    first = migrate(db_path)
    second = migrate(db_path)
    assert second == []
    assert len(first) == len(_list_migration_files())


def test_schema_version_is_append_only(tmp_path):
    db_path = tmp_path / "test.db"
    migrate(db_path)
    with open_connection(db_path) as conn:
        rows = conn.execute("SELECT version FROM schema_version ORDER BY id").fetchall()
        assert [r["version"] for r in rows] == sorted(r["version"] for r in rows)
        assert conn.execute("SELECT COUNT(*) AS c FROM schema_version").fetchone()["c"] >= 1
