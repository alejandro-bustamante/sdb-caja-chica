"""Web (Pyodide) entry point produced by ``flet publish``.

The Flet web worker boots Pyodide and runs this module via
``runpy.run_module("main")``. On the browser this module:

  1. loads the ``sqlite3`` package (Pyodide's CPython does not ship ``_sqlite3``
     by default, so it must be loaded before anything imports ``sqlite3``);
  2. migrates the fresh in-memory ledger and seeds it with demo data so the
     hosted demo is not empty;
  3. hands control to the real application (``app.main.main``).

On the desktop, running this file directly is equivalent to ``app.main``.
"""

from __future__ import annotations

import sys


def _load_sqlite3_package() -> None:
    """Load Pyodide's ``sqlite3`` package before any app import touches it."""
    if sys.platform != "emscripten":
        return
    import pyodide_js

    pyodide_js.loadPackage("sqlite3").syncify()


def _seed_demo_if_empty() -> None:
    """Migrate and seed a fresh browser ledger; no-op on the desktop."""
    if sys.platform != "emscripten":
        return
    from app.db.connection import migrate, open_connection
    from app.db.demo_seed import is_empty, seed_demo
    from app.main import resolve_db_path

    db_path = resolve_db_path()
    migrate(db_path)
    conn = open_connection(db_path)
    try:
        if is_empty(conn):
            seed_demo(conn)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    _load_sqlite3_package()
    _seed_demo_if_empty()

    import flet as ft

    from app.main import main as run_app

    ft.app(run_app)


if __name__ == "__main__":
    main()
