"""Headless smoke tests for the minimal app shell (Task 4)."""

from __future__ import annotations

import flet as ft

from app.main import LEDGER_FILE_NAME, resolve_db_path
from app.ui import strings_es
from app.ui.components.balance_banner import build_balance_banner
from app.ui.components.user_bar import build_user_bar


def test_user_bar_and_balance_banner_build(monkeypatch):
    # Flet controls can be constructed without a live running app/window.
    bar = build_user_bar("Ana")
    banner = build_balance_banner(total_cents=1500, cash_cents=1000, qr_cents=500)
    assert isinstance(bar, ft.Control)
    assert isinstance(banner, ft.Control)


def test_views_build_with_stub_page(conn, user_id, monkeypatch):
    class StubPage:
        def update(self):
            pass

    from app.ui.views.home import build_home
    from app.ui.views.user_picker import build_user_picker

    page = StubPage()
    selected = []

    picker = build_user_picker(page, conn, selected.append)
    assert isinstance(picker, ft.Control)

    home = build_home(page, conn, user_id)
    assert isinstance(home, ft.Control)


def test_resolve_db_path_uses_env_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SDB_CAJA_CHICA_DATA_DIR", str(tmp_path))
    assert resolve_db_path() == tmp_path / LEDGER_FILE_NAME
    assert (tmp_path / LEDGER_FILE_NAME).parent.exists()


def test_resolve_db_path_defaults_to_dev_data(monkeypatch, tmp_path):
    monkeypatch.delenv("SDB_CAJA_CHICA_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    path = resolve_db_path()
    assert "dev-data" in path.parts


def test_required_strings_exist():
    for key in [
        "APP_TITLE",
        "USER_PICKER_TITLE",
        "USER_PICKER_PROMPT",
        "USER_PICKER_CREATE_LABEL",
        "BALANCE_LABEL",
        "CURRENT_USER_LABEL",
    ]:
        assert getattr(strings_es, key) is not None


def test_migrate_works_on_resolved_dev_path(monkeypatch, tmp_path):
    from app.db.connection import iter_tables, migrate, open_connection

    monkeypatch.delenv("SDB_CAJA_CHICA_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    db_path = resolve_db_path()
    migrate(db_path)
    with open_connection(db_path) as conn:
        assert "sales" in iter_tables(conn)
