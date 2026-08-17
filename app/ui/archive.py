"""Archived-ledger session state (plan-04 Task 4).

Owns the lifecycle of the read-only archived-ledger view: opening a source
``.db`` file stages a migrated throwaway copy (``prepare_archived_copy``),
holds the read-only connection to it, and ``close()`` restores the live
session and deletes the temp copy. Kept free of Flet so the full
open -> browse -> export -> close cycle is unit-testable without booting the
UI (plan-04 Task 6.3).
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.db.connection import open_readonly_connection, prepare_archived_copy
from app.ui.session import Session


@dataclass
class ArchivedLedger:
    """An open archived ledger: read-only connection + the staged copy path."""

    conn: sqlite3.Connection
    copy_path: Path
    display_name: str


class ArchiveSessionManager:
    """Swaps the running app between the live ledger and one archived ledger.

    Only one archived ledger can be open at a time; opening another (or the
    live session) implicitly closes the previous one. ``session()`` returns a
    ``read_only=True`` session while an archive is open, and the plain live
    session otherwise — views never need to know which one they got.
    """

    def __init__(self, live_conn: sqlite3.Connection, live_session: Session) -> None:
        self._live_conn = live_conn
        self._live_session = live_session
        self._current: ArchivedLedger | None = None
        self._tmp_dir: Path | None = None

    @property
    def active(self) -> bool:
        """True while an archived ledger is open (read-only mode)."""
        return self._current is not None

    @property
    def current(self) -> ArchivedLedger | None:
        return self._current

    def session(self) -> Session:
        """The session views should use right now."""
        if self._current is not None:
            return Session(
                user_id=self._live_session.user_id,
                user_name=self._live_session.user_name,
                read_only=True,
            )
        return self._live_session

    def open(self, source_path: str | Path) -> ArchivedLedger:
        """Open an archived ledger file read-only; closes any previous one."""
        self.close()
        tmp_dir = Path(tempfile.mkdtemp(prefix="sdb_archive_"))
        copy_path = prepare_archived_copy(source_path, tmp_dir)
        conn = open_readonly_connection(copy_path)
        self._current = ArchivedLedger(
            conn=conn,
            copy_path=copy_path,
            display_name=Path(source_path).name,
        )
        self._tmp_dir = tmp_dir
        return self._current

    def close(self) -> None:
        """Restore the live session and delete the staged temp copy."""
        if self._current is None:
            return
        try:
            self._current.conn.close()
        finally:
            if self._tmp_dir is not None:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._current = None
            self._tmp_dir = None
