"""Unit tests for the on-demand backup / archive services (plan-03 Task 7)."""

from __future__ import annotations

import sqlite3

from app.db.repositories.users import create_user
from app.services import backup


def test_backup_database_folds_pending_writes(db_path, conn, tmp_path):
    """Backup is a self-contained copy that includes writes still in the WAL."""
    create_user(conn, "Blanca")
    destination = backup.backup_database(db_path, tmp_path / "backups")

    assert destination.exists()
    assert destination.name.startswith("ledger_backup_")
    assert destination.suffix == ".db"

    copied = sqlite3.connect(str(destination))
    try:
        count = copied.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        copied.close()
    assert count == 1


def test_backup_database_creates_missing_backup_dir(db_path, tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    destination = backup.backup_database(db_path, nested)
    assert destination.parent == nested
    assert destination.exists()


def test_next_archive_path_returns_unused_timestamped_name(tmp_path):
    first = backup.next_archive_path(tmp_path)
    assert first.name.startswith("ledger_")
    assert first.suffix == ".db"
    assert not first.exists()

    first.touch()
    second = backup.next_archive_path(tmp_path)
    assert second != first
    assert not second.exists()
