"""Application shell: persistent user bar + balance banner mounted once, a
navigation rail switching a single content area between the daily-use screens,
and a menu holding the backup (\"Copiar respaldo\"), archive-and-new-ledger, and
archived-ledger viewer (\"Abrir ledger archivado…\" / \"Cerrar ledger archivado\").

Per AGENTS.md §7 the header elements are structural, not per-screen. The shell
also owns a mutable connection holder so the archive action (DESIGN.md §3.9,
plan-03 Task 5) can swap the running app's ledger file without a restart, and
the archived-ledger viewer (plan-04 Task 4) can temporarily serve a read-only
copy of an old ledger with the exact same six screens.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import flet as ft

from app.db.connection import migrate, open_connection
from app.services import backup
from app.ui import strings_es
from app.ui.archive import ArchiveSessionManager
from app.ui.components.archive_banner import ArchiveBanner
from app.ui.components.balance_banner import BalanceBanner
from app.ui.components.user_bar import build_user_bar
from app.ui.session import Session
from app.ui.views import (
    audit as audit_view,
)
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
    "audit": audit_view.build,
}

class _ConnectionHolder:
    """Mutable reference to the live ledger connection.

    Views read ``holder.conn`` at build time; the archive action swaps it so
    every screen (and the banner) starts serving the new empty ledger file
    without restarting the app, and the archived-ledger viewer swaps it to a
    read-only copy of an old ledger (restored on close).
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
    archive = ArchiveSessionManager(conn, session)
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
        # ``archive.session()`` is the live session normally and a read-only
        # session while an archived ledger is open, so every view picks up the
        # right mode without any per-screen shell logic.
        content_area.content = builder(
            holder.conn, archive.session(), refresh_balance, page=page
        )
        _paint_rail(key)
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

    # --- Header: user bar (live) / SOLO LECTURA banner (archive) ------------

    user_bar = build_user_bar(session.user_name)
    archive_banner = ArchiveBanner()
    header_row = ft.Row([user_bar], spacing=0)

    def _refresh_header() -> None:
        if archive.active:
            assert archive.current is not None
            archive_banner.set_filename(archive.current.display_name)
            header_row.controls = [archive_banner.control, menu]
        else:
            header_row.controls = [user_bar, menu]
        if page is not None:
            page.update()

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

    async def _on_open_archive(e) -> None:
        picker = ft.FilePicker()
        try:
            files = await picker.pick_files(
                dialog_title=strings_es.MENU_OPEN_ARCHIVE,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["db"],
                allow_multiple=False,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            _show_message(strings_es.ARCHIVE_OPEN_ERROR.format(message=exc), is_error=True)
            return
        if not files:
            return  # user cancelled the picker
        try:
            archive.open(files[0].path)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            _show_message(strings_es.ARCHIVE_OPEN_ERROR.format(message=exc), is_error=True)
            return
        assert archive.current is not None
        holder.conn = archive.current.conn
        banner.refresh(holder.conn)
        _refresh_header()
        _refresh_menu()
        switch(current_key)

    def _on_close_archive(e) -> None:
        archive.close()
        holder.conn = conn  # back to the original live ledger connection
        banner.refresh(holder.conn)
        _refresh_header()
        _refresh_menu()
        switch(current_key)
        _show_message(strings_es.ARCHIVE_CLOSED, is_error=False)

    def _refresh_menu() -> None:
        if archive.active:
            # While browsing an archived ledger, opening a nested archive,
            # archiving the read-only view, or backing up a throwaway temp
            # copy are not meaningful actions — only "close" is offered
            # (plan-04 Task 4.5; deliberate scope decision, not an oversight).
            menu.items = [
                ft.PopupMenuItem(
                    icon=ft.Icons.CLOSE,
                    content=strings_es.MENU_CLOSE_ARCHIVE,
                    on_click=_on_close_archive,
                ),
            ]
        else:
            menu.items = [
                ft.PopupMenuItem(
                    icon=ft.Icons.SAVE_ALT,
                    content=strings_es.MENU_BACKUP,
                    on_click=_on_backup,
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.FOLDER_OPEN,
                    content=strings_es.MENU_OPEN_ARCHIVE,
                    on_click=_on_open_archive,
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.ARCHIVE,
                    content=strings_es.MENU_ARCHIVE,
                    on_click=_on_archive,
                ),
            ]
        if page is not None:
            page.update()

    # --- Navigation ----------------------------------------------------------

    # Custom rail (not ft.NavigationRail) so the selected destination can be a
    # full-width, high-contrast label spanning icon + text — a NavigationRail's
    # built-in indicator is only a small pill around the icon. The rail gets a
    # background clearly distinct from the page so it reads as a task bar.
    _NAV_DESTINATIONS = [
        ("sales", ft.Icons.POINT_OF_SALE, strings_es.NAV_VENTAS),
        ("catalog", ft.Icons.CATEGORY, strings_es.NAV_CATALOGO),
        ("restock", ft.Icons.INVENTORY_2, strings_es.NAV_RESTOCK),
        ("expenses", ft.Icons.RECEIPT_LONG, strings_es.NAV_GASTOS),
        ("debts", ft.Icons.ACCOUNT_BALANCE_WALLET, strings_es.NAV_FIADO),
        ("cash_counts", ft.Icons.CHECKLIST, strings_es.NAV_ARQUEO),
        ("export", ft.Icons.TABLE_CHART, strings_es.NAV_EXPORT),
        ("audit", ft.Icons.HISTORY, strings_es.NAV_AUDITORIA),
    ]

    rail_buttons: dict[str, ft.Container] = {}

    def _paint_rail(selected_key: str) -> None:
        """Repaint the rail so exactly the selected destination is highlighted."""
        for key, container in rail_buttons.items():
            selected = key == selected_key
            icon = container.content.controls[0]  # ft.Icon
            label = container.content.controls[1]  # ft.Text
            container.bgcolor = ft.Colors.PRIMARY if selected else None
            icon.color = (
                ft.Colors.ON_PRIMARY if selected else ft.Colors.ON_SURFACE_VARIANT
            )
            label.color = (
                ft.Colors.ON_PRIMARY if selected else ft.Colors.ON_SURFACE_VARIANT
            )
            label.weight = ft.FontWeight.BOLD if selected else ft.FontWeight.NORMAL

    def _make_destination(key: str, icon: str, label: str) -> ft.Container:
        container = ft.Container(
            content=ft.Row(
                [ft.Icon(icon, size=20), ft.Text(label, size=13)],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            border_radius=10,
            margin=ft.Margin.symmetric(horizontal=10, vertical=2),
            ink=True,
            on_click=lambda e, k=key: switch(k),
        )
        rail_buttons[key] = container
        return container

    rail = ft.Container(
        width=200,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Text(
                        strings_es.NAV_TITLE,
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    padding=ft.Padding.symmetric(horizontal=24, vertical=8),
                ),
                *(
                    _make_destination(key, icon, label)
                    for key, icon, label in _NAV_DESTINATIONS
                ),
            ],
            spacing=4,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.Padding.symmetric(vertical=8),
    )
    _paint_rail("sales")

    menu = ft.PopupMenuButton(
        icon=ft.Icons.MENU,
        tooltip=strings_es.MENU_ACTIONS,
        items=[],
    )

    header_row.controls = [user_bar, menu]
    _refresh_menu()
    switch("sales")

    return ft.Column(
        [
            header_row,
            banner.control,
            ft.Row(
                [
                    rail,
                    ft.VerticalDivider(width=1),
                    content_area,
                ],
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ],
        spacing=4,
        expand=True,
    )
