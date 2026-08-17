"""Tests for the archived-ledger connection machinery (plan-04 Tasks 1 & 2).

Covers ``prepare_archived_copy`` (original file preserved byte-for-byte, the
copy migrated to the latest schema, WAL sidecars folded in, newer-schema files
rejected), ``open_readonly_connection`` (SQLite-level read-only plus
``query_only``), and the ``transaction`` guard that raises
``ReadOnlyLedgerError`` before any repository write can run against a
read-only connection.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.db.connection import (
    MIGRATIONS_DIR,
    ArchivedLedgerTooNewError,
    ReadOnlyLedgerError,
    _execute_script_atomically,
    _list_migration_files,
    now,
    open_connection,
    open_readonly_connection,
    prepare_archived_copy,
)
from app.db.repositories import expenses as expenses_repo
from app.db.repositories import products as products_repo
from app.db.repositories import users as users_repo
from app.domain.types import ExpensePaymentInput

_LATEST = max(number for number, _ in _list_migration_files())


def _apply_migration_1_only(path) -> int:
    """A pre-migration fixture frozen at schema version 1, with a user and an
    expense (the pre-0003 shape: no ``expense_payments`` table yet)."""
    conn = open_connection(path)
    try:
        script = (MIGRATIONS_DIR / "0001_initial.sql").read_text(encoding="utf-8")
        _execute_script_atomically(conn, script, 1)
        user_id = conn.execute("INSERT INTO users (name) VALUES ('Alice')").lastrowid
        conn.execute(
            "INSERT INTO expenses (logical_id, version, timestamp, user_id,"
            " description, amount) VALUES (1, 1, ?, ?, 'Luz', 5000)",
            (now(), user_id),
        )
        conn.commit()
    finally:
        conn.close()
    return user_id


def test_prepare_archived_copy_migrates_copy_and_preserves_original(tmp_path):
    source = tmp_path / "old.db"
    _apply_migration_1_only(source)
    before = source.read_bytes()

    copy = prepare_archived_copy(source, tmp_path / "staged")

    # The original fixture file is byte-for-byte unchanged.
    assert source.read_bytes() == before
    # The copy exists separately and is migrated to the latest schema.
    assert copy != source
    assert copy.exists()
    with open_connection(copy) as conn:
        current = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert current == _LATEST
        # Pre-existing data is intact.
        row = conn.execute(
            "SELECT description FROM expenses WHERE logical_id = 1"
        ).fetchone()
        assert row["description"] == "Luz"
        # ...and readable through the existing repository read functions.
        users = users_repo.list_active_users(conn)
        assert [u.name for u in users] == ["Alice"]
        expenses = expenses_repo.list_current_expenses(conn)
        assert len(expenses) == 1
        assert expenses[0]["amount"] == 5000


def test_prepare_archived_copy_folds_wal_sidecar_into_copy(tmp_path):
    """A write still sitting in the source's WAL must land in the copy."""
    source = tmp_path / "wal.db"
    from app.db.connection import migrate

    migrate(source)
    writer = open_connection(source)
    try:
        writer.execute("INSERT INTO users (name) VALUES ('InWal')")
        # writer stays open, so the row lives only in the -wal sidecar.
        copy = prepare_archived_copy(source, tmp_path / "staged")
    finally:
        writer.close()

    with open_connection(copy) as conn:
        names = [
            r["name"] for r in conn.execute("SELECT name FROM users").fetchall()
        ]
    assert "InWal" in names


def test_prepare_archived_copy_rejects_newer_schema(tmp_path):
    """A file from a *newer* app version is refused, never guessed at."""
    source = tmp_path / "newer.db"
    from app.db.connection import migrate

    migrate(source)
    with open_connection(source) as conn:
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (_LATEST + 1, now()),
        )
    before = source.read_bytes()

    with pytest.raises(ArchivedLedgerTooNewError):
        prepare_archived_copy(source, tmp_path / "staged")
    assert source.read_bytes() == before


def test_open_readonly_connection_is_query_only(db_path):
    conn = open_readonly_connection(db_path)
    try:
        row = conn.execute("PRAGMA query_only").fetchone()
        assert int(row[0]) == 1
        # Belt-and-suspenders: even raw SQL cannot write through this
        # connection (the URI mode=ro guard, independent of query_only).
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO users (name) VALUES ('Nope')")
    finally:
        conn.close()


def test_write_repo_functions_raise_readonly_error(db_path):
    """Every repository write raises ReadOnlyLedgerError against a read-only
    connection, before any SQL runs — no row is ever inserted (plan-04 Task 2
    exit criteria)."""
    conn = open_connection(db_path)
    try:
        user_id = users_repo.create_user(conn, "Alice")
        product_id = products_repo.create_product(conn, "Azúcar", 1000, user_id)
    finally:
        conn.close()

    ro = open_readonly_connection(db_path)
    try:
        with pytest.raises(ReadOnlyLedgerError):
            expenses_repo.create_expense(
                ro, "Luz", [ExpensePaymentInput("cash", 100)], user_id
            )
        with pytest.raises(ReadOnlyLedgerError):
            products_repo.set_product_active(ro, product_id, False, user_id)
        with pytest.raises(ReadOnlyLedgerError):
            users_repo.set_user_active(ro, user_id, False)
        with pytest.raises(ReadOnlyLedgerError):
            users_repo.create_user(ro, "Bob")
    finally:
        ro.close()

    with open_connection(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"] == 1
        users = [r["name"] for r in conn.execute("SELECT name FROM users").fetchall()]
        assert users == ["Alice"]
        # products.active was not flipped by the guarded write.
        active = conn.execute(
            "SELECT active FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        assert active["active"] == 1
