"""Application shell: persistent user bar + balance banner mounted once, a
navigation rail switching a single content area between the daily-use screens,
and a menu holding the backup ("Copiar respaldo") and archive-and-new-ledger
actions.

Per AGENTS.md §7 the header elements are structural, not per-screen. The shell
also owns a mutable connection holder so the archive action (DESIGN.md §3.9,
plan-03 Task 5) can swap the running app's ledger file without a restart.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import flet as ft

from app.db.connection import migrate, open_connection
from app.services import backup
from app.ui import strings_es
from app.ui.components.balance_banner import BalanceBanner
from app.ui.components.user_bar import build_user_bar
from app.ui.session import Session
from app.ui.views import cash_counts, catalog, debts, expenses, export, restock
from app.ui.views import (
    sales as sales_view,
)

_VIEW_BUILDERS = {
    "sales": sales_view.build,
    "catalog": catalog.build,
    "restock": restock.build,
    "expenses": expenses.build,
    "debts": debts.build,
    "cash_counts": cash_counts.build,
    "export": export.build,
}

_ORDER = ["sales", "catalog", "restock", "expenses", "debts", "cash_counts", "export"]


class _ConnectionHolder:
    """Mutable reference to the live ledger connection.

    Views read ``holder.conn`` at build time; the archive action swaps it so
    every screen (and the banner) starts serving the new empty ledger file
    without restarting the app.
    """

    def __init__(self, conn) -> None:
        self.conn = conn


def _db_file_path(conn) -> Path | None:
    """The on-disk path of the passed ledger connection, if any."""
    row = conn.execute("PRAGMA database_list").fetchone()
    name = str(row["name"] if row else "")
    if not name or name == ":memory:":
        return None
    return Path(name)


def build_shell(
    page: ft.Page, conn, session: Session
) -> ft.Control:
    holder = _ConnectionHolder(conn)
    current_key = "sales"

    banner = BalanceBanner()
    banner.refresh(holder.conn)

    def refresh_balance() -> None:
        """Shared callback: recompute the banner after any write / nav change."""
        banner.refresh(holder.conn)
        if page is not None:
            page.update()

    content_area = ft.Container(expand=True)

    def switch(key: str) -> None:
        nonlocal current_key
        current_key = key
        builder: Callable = _VIEW_BUILDERS[key]
        content_area.content = builder(holder.conn, session, refresh_balance, page=page)
        if page is not None:
            page.update()

    def reload_all() -> None:
        """Rebuild the current screen and banner against the restored conn."""
        banner.refresh(holder.conn)
        switch(current_key)

    def _show_message(message: str, *, is_error: bool) -> None:
        if page is None:
            return
        color = ft.Colors.RED_900 if is_error else ft.Colors.GREEN_900
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(strings_es.MENU_ACTIONS),
            content=ft.Text(message, color=color),
            actions=[
                ft.TextButton(strings_es.COMMON_CLOSE, on_click=lambda e: _close(dialog)),
            ],
        )

        def _close(dlg) -> None:
            if page is not None:
                page.pop_dialog()
                page.update()

        page.show_dialog(dialog)

    # --- Menu actions --------------------------------------------------------

    def _on_backup(e) -> None:
        try:
            source = _db_file_path(holder.conn)
            if source is None:
                raise RuntimeError("No on-disk ledger to back up.")
            destination = backup.backup_database(source, source.parent)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            _show_message(strings_es.BACKUP_ERROR.format(message=exc), is_error=True)
            return
        _show_message(strings_es.BACKUP_SUCCESS.format(path=destination), is_error=False)

    def _on_archive(e) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(strings_es.ARCHIVE_TITLE),
            content=ft.Text(strings_es.ARCHIVE_QUESTION),
            actions=[
                ft.TextButton(
                    strings_es.COMMON_CANCEL, on_click=lambda e: _close(dialog)
                ),
                ft.TextButton(strings_es.ARCHIVE_CONFIRM, on_click=lambda e: _do_archive(dialog)),
            ],
        )

        def _do_archive(dlg) -> None:
            try:
                current_path = _db_file_path(holder.conn)
                data_dir = current_path.parent if current_path is not None else Path("dev-data")
                new_path = backup.next_archive_path(data_dir)
                migrate(new_path)
                new_conn = open_connection(new_path)
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                _close(dlg)
                _show_message(strings_es.ARCHIVE_ERROR.format(message=exc), is_error=True)
                return
            old_conn = holder.conn
            holder.conn = new_conn
            old_conn.close()
            _close(dlg)
            reload_all()
            _show_message(strings_es.ARCHIVE_SUCCESS.format(path=new_path), is_error=False)

        def _close(dlg) -> None:
            if page is not None:
                page.pop_dialog()
                page.update()

        if page is not None:
            page.show_dialog(dialog)

    # --- Navigation ----------------------------------------------------------

    destinations = [
        ft.NavigationRailDestination(
            icon=ft.Icons.POINT_OF_SALE, label=strings_es.NAV_VENTAS
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.CATEGORY, label=strings_es.NAV_CATALOGO
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.INVENTORY_2, label=strings_es.NAV_RESTOCK
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.RECEIPT_LONG, label=strings_es.NAV_GASTOS
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.ACCOUNT_BALANCE_WALLET, label=strings_es.NAV_FIADO
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.CHECKLIST, label=strings_es.NAV_ARQUEO
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.TABLE_CHART, label=strings_es.NAV_EXPORT
        ),
    ]

    def on_nav_change(e) -> None:
        index = e.control.selected_index
        if 0 <= index < len(_ORDER):
            switch(_ORDER[index])

    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=110,
        width=110,
        destinations=destinations,
        on_change=on_nav_change,
    )

    menu = ft.PopupMenuButton(
        icon=ft.Icons.MENU,
        tooltip=strings_es.MENU_ACTIONS,
items=[
            ft.PopupMenuItem(
                content=strings_es.MENU_BACKUP, on_click=_on_backup
            ),
            ft.PopupMenuItem(
                content=strings_es.MENU_ARCHIVE, on_click=_on_archive
            ),
        ],
    )

    switch("sales")

    return ft.Column(
        [
            ft.Row([build_user_bar(session.user_name), menu], spacing=0),
            banner.control,
            ft.Row(
                [
                    rail,
                    ft.VerticalDivider(width=1),
                    content_area,
                ],
                expand=True,
                spacing=0,
            ),
        ],
        spacing=4,
        expand=True,
    )
