"""SQLite connection setup, transaction helper, and migration runner.

This module is the single place that configures a SQLite connection and the
transaction discipline every repository write must go through (AGENTS.md §4).
No ORM is used anywhere — raw ``sqlite3`` only (AGENTS.md §2).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def open_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with the PRAGMAs required by DESIGN.md §5.2.

    ``row_factory`` is set to :class:`sqlite3.Row` so repository code can use
    named column access.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = FULL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    """Commits on success, rolls back on any exception.

    Every multi-table write must run through this helper so a failed operation
    can never leave a partially-written state behind (AGENTS.md §4).
    """
    try:
        cur = conn.execute("BEGIN")
        yield cur
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def _list_migration_files() -> list[tuple[int, Path]]:
    """Return sorted ``(number, path)`` pairs for every ``NNNN_*.sql`` file."""
    migrations: list[tuple[int, Path]] = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        stem = path.name.split("_", 1)[0]
        try:
            number = int(stem)
        except ValueError:
            logger.warning("Ignoring non-numeric migration file %s", path.name)
            continue
        migrations.append((number, path))
    migrations.sort(key=lambda item: item[0])
    return migrations


def _current_version(conn: sqlite3.Connection) -> int | None:
    """Return the highest applied migration version, or ``None`` if fresh."""
    try:
        cur = conn.execute(
            "SELECT COALESCE(MAX(version), NULL) FROM schema_version"
        )
        return cur.fetchone()[0]
    except sqlite3.Error as exc:
        if "no such table: schema_version" in str(exc):
            return None
        raise


def _split_statements(script: str) -> list[str]:
    """Split a migration script into individual statements.

    Strips ``--`` comment lines (migrations never rely on inline comment
    handling), then splits on ``;``. Migration scripts contain only plain
    DDL (CREATE TABLE / CREATE INDEX), so this is safe.
    """
    lines = [
        line
        for line in script.splitlines()
        if not line.strip().startswith("--") and line.strip()
    ]
    joined = "\n".join(lines)
    return [stmt.strip() for stmt in joined.split(";") if stmt.strip()]


def _execute_script_atomically(
    conn: sqlite3.Connection, script: str, number: int
) -> None:
    """Run one migration inside a real transaction.

    ``executescript`` implicitly commits pending transactions in autocommit
    mode, which would break per-migration atomicity — so statements are run
    one by one inside an explicit BEGIN/COMMIT instead (AGENTS.md §4).
    """
    conn.execute("BEGIN")
    try:
        for statement in _split_statements(script):
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (number, int(__import__("time").time())),
        )
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def migrate(db_path: str | Path) -> list[int]:
    """Apply any pending migrations in order, each in its own transaction.

    Runs one transaction per migration file, executing the script and recording
    it in ``schema_version`` atomically. Returns the list of applied numbers.
    """
    applied: list[int] = []
    with open_connection(db_path) as conn:
        for number, path in _list_migration_files():
            if number <= (_current_version(conn) or 0):
                continue
            script = path.read_text(encoding="utf-8")
            _execute_script_atomically(conn, script, number)
            applied.append(number)
    logger.info("Applied migrations: %s", applied or ["none"])
    return applied


def iter_tables(conn: sqlite3.Connection) -> set[str]:
    """Return the set of user table names present in the database."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row["name"] for row in rows}


def now() -> int:
    """Integer unix timestamp, used for every ``timestamp`` column."""
    import time

    return int(time.time())


def rowid(cur: sqlite3.Cursor) -> int:
    """Return the last insert rowid, raising if unavailable.

    ``lastrowid`` is ``None`` until an INSERT actually ran, so repository code
    boxes it through here to keep type checkers happy and fail loudly.
    """
    value = cur.lastrowid
    assert value is not None, "no lastrowid available"
    return int(value)
