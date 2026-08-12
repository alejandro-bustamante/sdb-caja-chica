"""On-demand database backup — DESIGN.md §5.2, plan-03 Task 4.

A plain file copy of the current SQLite ledger into a timestamped filename
inside ``backup_dir``. Because the DB runs in WAL mode, the copy is preceded by
``PRAGMA wal_checkpoint(TRUNCATE)`` so the resulting file is self-contained and
carries no uncommitted WAL data. No automatic schedule — this is a manual,
on-demand action (DESIGN.md §7).
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

_FILE_STEM = "ledger_backup"


def _checkpoint_wal(source_path: str | Path) -> None:
    """Fold the WAL into the main DB file via a temporary connection."""
    conn = sqlite3.connect(str(source_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def backup_database(source_path: str | Path, backup_dir: str | Path) -> Path:
    """Copy ``source_path`` into ``backup_dir`` with a timestamped name.

    Returns the created backup file path. A WAL checkpoint runs first so the
    copy is complete even right after a write (the app's own connection may
    still hold a live WAL file).
    """
    source = Path(source_path)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = target_dir / f"{_FILE_STEM}_{timestamp}.db"
    _checkpoint_wal(source)
    shutil.copy2(source, destination)
    return destination


def next_archive_path(data_dir: str | Path) -> Path:
    """A fresh, never-existing ledger file path in ``data_dir``.

    Used by the "archive and start a new ledger" action: the current file stays
    untouched and a new empty file is created at this timestamped path (plan-03
    Task 5). The running app switches its connection to the returned path.
    """
    target_dir = Path(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    counter = 0
    while True:
        name = f"ledger_{timestamp}{f'_{counter}' if counter else ''}.db"
        candidate = target_dir / name
        if not candidate.exists():
            return candidate
        counter += 1
