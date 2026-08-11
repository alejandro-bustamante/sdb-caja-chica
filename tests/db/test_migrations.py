"""Tests for the migration runner and schema application (Task 1)."""

from __future__ import annotations

from app.db.connection import (
    MIGRATIONS_DIR,
    _execute_script_atomically,
    _list_migration_files,
    iter_tables,
    migrate,
    now,
    open_connection,
)

EXPECTED_TABLES = {
    "users",
    "products",
    "product_prices",
    "expenses",
    "expense_payments",
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


def test_migration_0003_backfills_cash_payments_for_existing_expenses(tmp_path):
    """Upgrading a pre-0003 DB keeps balances identical: every existing
    expense version gets a matching cash payment row."""
    db_path = tmp_path / "upgrade.db"

    conn = open_connection(db_path)
    script = (MIGRATIONS_DIR / "0001_initial.sql").read_text(encoding="utf-8")
    _execute_script_atomically(conn, script, 1)
    user_id = conn.execute("INSERT INTO users (name) VALUES ('Alice')").lastrowid
    conn.execute(
        "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
        " description, amount) VALUES (1, 1, ?, ?, 'Luz', 5000)",
        (now(), user_id),
    )
    conn.execute(
        "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
        " description, amount, superseded_at) VALUES (1, 2, ?, ?, 'Luz', 4800, ?)",
        (now(), user_id, now()),
    )
    conn.commit()
    conn.close()

    applied = migrate(db_path)
    assert 3 in applied

    with open_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT ep.expense_id, ep.method, ep.amount"
            " FROM expense_payments ep ORDER BY ep.expense_id"
        ).fetchall()
        assert len(rows) == 2
        assert [(r["method"], r["amount"]) for r in rows] == [("cash", 5000), ("cash", 4800)]


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


def test_migration_0002_links_batch_to_expense_logical_id(tmp_path):
    """An existing DB on 0001 upgrades cleanly, backfilling the logical_id."""
    db_path = tmp_path / "upgrade.db"

    # Apply only 0001, then seed a user, an expense and a batch pointing at the
    # expense's physical row id (the pre-0002 shape).
    conn = open_connection(db_path)
    script = (MIGRATIONS_DIR / "0001_initial.sql").read_text(encoding="utf-8")
    _execute_script_atomically(conn, script, 1)
    user = conn.execute("INSERT INTO users (name) VALUES ('Alice')")
    user_id = user.lastrowid
    conn.execute(
        "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
        " description, amount) VALUES (1, 1, ?, ?, 'Repo', 5000)",
        (now(), user_id),
    )
    conn.execute(
        "INSERT INTO batches (timestamp, user_id, expense_id) VALUES (?, ?, 1)",
        (now(), user_id),
    )
    conn.commit()
    conn.close()

    applied = migrate(db_path)
    assert applied == [2, 3]

    with open_connection(db_path) as conn:
        (row,) = conn.execute(
            "SELECT expense_logical_id FROM batches"
        ).fetchall()
        assert row["expense_logical_id"] == 1
        cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(batches)")
        }
        assert "expense_logical_id" in cols
        assert "expense_id" not in cols
