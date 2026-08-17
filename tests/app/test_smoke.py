"""Headless smoke tests for the app shell and views (plan Task 1, Task 8)."""

from __future__ import annotations

import flet as ft

from app.main import LEDGER_FILE_NAME, resolve_db_path
from app.ui import strings_es
from app.ui.components.balance_banner import BalanceBanner, build_balance_banner
from app.ui.components.user_bar import build_user_bar


def test_user_bar_and_balance_banner_build(monkeypatch):
    # Flet controls can be constructed without a live running app/window.
    bar = build_user_bar("Ana")
    banner = build_balance_banner(total_cents=1500, cash_cents=1000, qr_cents=500)
    assert isinstance(bar, ft.Control)
    assert isinstance(banner, ft.Control)


def test_reactive_balance_banner_refreshes_from_conn(conn, user_id):
    banner = BalanceBanner()
    assert isinstance(banner.control, ft.Control)
    banner.refresh(conn)
    assert banner.control.content
    total_text = banner.control.content.controls[1]
    assert "$ 0.00" in total_text.value


def test_views_build_with_stub_page(conn, user_id, monkeypatch):
    class StubPage:
        def update(self):
            pass

        def show_dialog(self, dialog):
            pass

        def pop_dialog(self, dialog=None):
            pass

        overlay = []

    from app.ui.session import Session
    from app.ui.shell import build_shell
    from app.ui.views import (
        audit,
        cash_counts,
        catalog,
        debts,
        expenses,
        export,
        restock,
        sales,
    )
    from app.ui.views.user_picker import build_user_picker

    session = Session(user_id=user_id, user_name="Alice")
    page = StubPage()
    selected = []

    picker = build_user_picker(page, conn, selected.append)
    assert isinstance(picker, ft.Control)

    calls = []

    def on_change():
        calls.append(1)

    controls = {
        "sales": sales.build(conn, session, on_change, page=page),
        "catalog": catalog.build(conn, session, on_change, page=page),
        "restock": restock.build(conn, session, on_change, page=page),
        "expenses": expenses.build(conn, session, on_change, page=page),
        "debts": debts.build(conn, session, on_change, page=page),
        "cash_counts": cash_counts.build(conn, session, on_change, page=page),
        "export": export.build(conn, session, on_change, page=page),
        "audit": audit.build(conn, session, on_change, page=page),
    }
    for name, control in controls.items():
        assert isinstance(control, ft.Control), name
        assert calls == []

    shell = build_shell(page, conn, session)
    assert isinstance(shell, ft.Control)


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
    required = [
        "APP_TITLE",
        "USER_PICKER_TITLE",
        "USER_PICKER_PROMPT",
        "USER_PICKER_CREATE_LABEL",
        "BALANCE_LABEL",
        "CURRENT_USER_LABEL",
        "NAV_VENTAS",
        "NAV_CATALOGO",
        "NAV_RESTOCK",
        "NAV_GASTOS",
        "NAV_FIADO",
        "NAV_ARQUEO",
        "NAV_AUDITORIA",
        "SALES_TITLE",
        "CATALOG_TITLE",
        "RESTOCK_TITLE",
        "EXPENSES_TITLE",
        "DEBTS_TITLE",
        "ARQUEO_TITLE",
    ]
    for key in required:
        assert getattr(strings_es, key) is not None


def test_migrate_works_on_resolved_dev_path(monkeypatch, tmp_path):
    from app.db.connection import iter_tables, migrate, open_connection

    monkeypatch.delenv("SDB_CAJA_CHICA_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    db_path = resolve_db_path()
    migrate(db_path)
    with open_connection(db_path) as conn:
        assert "sales" in iter_tables(conn)
