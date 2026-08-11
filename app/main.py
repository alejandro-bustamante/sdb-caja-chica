"""Application entry point.

Resolves the SQLite ledger path, runs pending migrations, and launches the
Flet shell (mandatory user picker -> app shell with persistent user bar +
total available balance banner and navigation across the daily-use screens).
"""

from __future__ import annotations

import os
from pathlib import Path

import flet as ft

from app.db.connection import migrate, open_connection
from app.db.repositories import users as users_repo
from app.ui import strings_es
from app.ui.session import Session
from app.ui.shell import build_shell
from app.ui.views.user_picker import build_user_picker

APP_NAME = "SDB Caja Chica"
LEDGER_FILE_NAME = "ledger.db"

# Override for testing / dev / custom deployments. In production this is set
# (e.g. packaged as %USERPROFILE%\\Documents\\<APP_NAME>) so the ledger lives
# under the user's Documents folder per DESIGN.md §5.3.
_DATA_DIR_ENV = "SDB_CAJA_CHICA_DATA_DIR"


def resolve_db_path() -> Path:
    """Return the ledger file path, creating its parent folder if needed."""
    env_dir = os.environ.get(_DATA_DIR_ENV)
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path(__file__).resolve().parent.parent / "dev-data"
    base.mkdir(parents=True, exist_ok=True)
    return base / LEDGER_FILE_NAME


def main(page: ft.Page) -> None:
    page.title = strings_es.APP_TITLE

    db_path = resolve_db_path()
    migrate(db_path)
    conn = open_connection(db_path)

    def on_user_selected(user_id: int) -> None:
        user = users_repo.get_user(conn, user_id)
        assert user is not None
        session = Session(user_id=user.id, user_name=user.name)
        page.clean()
        page.add(build_shell(page, conn, session))

    def show_picker() -> None:
        page.clean()
        page.add(build_user_picker(page, conn, on_user_selected))

    show_picker()


if __name__ == "__main__":
    ft.app(main)
