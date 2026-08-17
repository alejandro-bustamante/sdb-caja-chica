"""SQLite connection setup, transaction helper, and migration runner.

This module is the single place that configures a SQLite connection and the
transaction discipline every repository write must go through (AGENTS.md §4).
No ORM is used anywhere — raw ``sqlite3`` only (AGENTS.md §2).

It also owns the archived-ledger read-only machinery (plan-04 Task 1):
``prepare_archived_copy`` stages a *copy* of an old ledger file and migrates
that copy (never the original), and ``open_readonly_connection`` opens any
path with the file locked read-only at the SQLite level plus ``query_only``
as a second guard. The ``transaction`` helper refuses to start against a
``query_only`` connection, so no repository write can silently no-op against
an archived ledger (AGENTS.md §1).
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.ui import strings_es

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class ReadOnlyLedgerError(RuntimeError):
    """Raised when a write is attempted against a ``query_only`` connection.

    Raised by :func:`transaction` before any SQL runs, so a repository write
    against an archived (read-only) ledger fails loudly instead of silently
    no-op'ing (plan-04 Task 2).
    """


class ArchivedLedgerTooNewError(RuntimeError):
    """Raised when an archived file's schema is newer than this app version.

    The app refuses to guess at a schema it does not know how to read — it
    never attempts to "downgrade" an archived file (plan-04 Task 1).
    """


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


def _assert_writable(conn: sqlite3.Connection) -> None:
    """Raise :class:`ReadOnlyLedgerError` if ``query_only`` is ON.

    This is the single choke point that makes every repository write fail
    fast against an archived ledger connection (plan-04 Task 2). The check
    happens before any SQL runs — a write is never allowed to silently no-op.
    """
    row = conn.execute("PRAGMA query_only").fetchone()
    if row is not None and int(row[0]) == 1:
        raise ReadOnlyLedgerError(
            "Cannot write: connection is read-only (query_only is ON)."
        )


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    """Commits on success, rolls back on any exception.

    Every multi-table write must run through this helper so a failed operation
    can never leave a partially-written state behind (AGENTS.md §4). Refuses
    to start against a ``query_only`` connection (see :func:`_assert_writable`).
    """
    _assert_writable(conn)
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

    The connection is closed explicitly: ``with sqlite3.Connection`` only
    commits/rolls back, it does *not* close, and a leaked WAL connection would
    checkpoint (i.e. modify) the database file whenever it is eventually
    garbage-collected — unacceptable for the archived-ledger viewer, which
    must never touch the archived file (plan-04 Task 1).
    """
    applied: list[int] = []
    conn = open_connection(db_path)
    try:
        for number, path in _list_migration_files():
            if number <= (_current_version(conn) or 0):
                continue
            script = path.read_text(encoding="utf-8")
            _execute_script_atomically(conn, script, number)
            applied.append(number)
    finally:
        conn.close()
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


def _latest_migration_number() -> int:
    """The highest migration version this app version knows how to apply."""
    return max(number for number, _ in _list_migration_files())


def _checkpoint_wal_into(path: str | Path) -> None:
    """Fold any ``-wal`` sidecar into the given DB file via a throwaway
    connection, so the file becomes self-contained (mirrors the backup logic
    from plan-03 Task 4, but always against the *copy*, never the original).
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def prepare_archived_copy(
    source_path: str | Path, tmp_dir: str | Path
) -> Path:
    """Stage a fully-migrated, self-contained copy of an archived ledger.

    The archived file on disk is **never** touched: the file (and any
    ``-wal``/``-shm`` sidecars) are copied into ``tmp_dir``, the copy's WAL is
    checkpointed into the copy, and the existing migration runner is applied
    against the copy (plan-04 Task 1, option (b)).

    # TODO(reviewer): confirm archived-file migration strategy — the default
    # is to migrate a throwaway copy (option (b) in plan-04 Task 1), so a
    # ledger archived by an older app version opens in the current one.

    Raises :class:`ArchivedLedgerTooNewError` if the copy's ``schema_version``
    is *ahead* of what this app version can read — the app refuses to guess at
    a newer schema rather than attempting a "downgrade".

    Returns the path of the staged copy (owned by the caller; delete it when
    the viewer closes).
    """
    source = Path(source_path)
    tmp = Path(tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)
    copy_path = tmp / source.name
    shutil.copy2(source, copy_path)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(source) + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, Path(str(copy_path) + suffix))
    _checkpoint_wal_into(copy_path)
    conn = open_connection(copy_path)
    try:
        version = _current_version(conn) or 0
    finally:
        conn.close()
    if version > _latest_migration_number():
        raise ArchivedLedgerTooNewError(strings_es.ARCHIVE_TOO_NEW_ERROR)
    migrate(copy_path)
    return copy_path


def open_readonly_connection(path: str | Path) -> sqlite3.Connection:
    """Open a connection that cannot write, two independent ways.

    The SQLite URI ``mode=ro`` locks the file read-only at the engine level
    (the on-disk file cannot be modified by this connection), and
    ``PRAGMA query_only = ON`` adds a second belt-and-suspenders guard that
    :func:`transaction` also checks before any write runs (plan-04 Task 1/2).
    """
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn
