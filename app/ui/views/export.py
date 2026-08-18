"""Excel export screen — date-range picker and an "Exportar" button that
writes the workbook to a user-chosen location via Flet's native file picker.

The FilePicker is a *Service* in Flet 0.80+: it self-registers on the page the
moment it is instantiated inside an event handler, and it must **not** be
appended to ``page.overlay`` (doing so makes the client reject it with
"Unknown control: FilePicker"). A fresh instance is created per export click.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from pathlib import Path

import flet as ft

from app.services import excel_export
from app.ui import strings_es
from app.ui.components.calendar_picker import CalendarDialog
from app.ui.session import Session
from app.ui.views import export_controller


def build(
    conn,
    session: Session,
    on_change: Callable[[], None],
    page: ft.Page | None = None,
) -> ft.Control:

    def _update() -> None:
        if page is not None:
            page.update()

    def _open_calendar(field: ft.TextField) -> None:
        """Show a calendar for the clicked field; the picked date fills it."""
        if page is None:
            return

        def _picked(date: datetime.date) -> None:
            field.value = date.strftime("%d/%m/%Y")
            _update()

        initial = export_controller.parse_date_text(field.value)
        CalendarDialog(page, initial, _picked).show()

    date_from_field = ft.TextField(
        label=strings_es.EXPORT_DATE_FROM_LABEL,
        hint_text="dd/mm/aaaa",
        width=190,
        read_only=True,
        suffix_icon=ft.Icons.CALENDAR_MONTH,
        on_click=lambda e: _open_calendar(date_from_field),
    )
    date_to_field = ft.TextField(
        label=strings_es.EXPORT_DATE_TO_LABEL,
        hint_text="dd/mm/aaaa",
        width=190,
        read_only=True,
        suffix_icon=ft.Icons.CALENDAR_MONTH,
        on_click=lambda e: _open_calendar(date_to_field),
    )
    export_button = ft.Button(strings_es.EXPORT_BUTTON, width=200)
    status_text = ft.Text("", color=ft.Colors.RED_700)

    async def _on_export(e) -> None:
        date_from, date_to, error = export_controller.validate_range(
            date_from_field.value, date_to_field.value
        )
        if error is not None or date_from is None or date_to is None:
            status_text.value = error or strings_es.EXPORT_INVALID_DATE
            status_text.color = ft.Colors.RED_700
            _update()
            return
        picker = ft.FilePicker()
        path = await picker.save_file(
            dialog_title=strings_es.EXPORT_TITLE,
            file_name=export_controller.default_file_name(date_from, date_to),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )
        if not path:
            return
        try:
            excel_export.export_range(conn, date_from, date_to, Path(path))
            status_text.value = strings_es.EXPORT_SUCCESS.format(path=path)
            status_text.color = ft.Colors.GREEN_700
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            status_text.value = strings_es.EXPORT_ERROR.format(message=exc)
            status_text.color = ft.Colors.RED_700
        _update()

    export_button.on_click = _on_export

    return ft.Container(
        padding=16,
        content=ft.Column(
            [
                ft.Text(strings_es.EXPORT_TITLE, size=20, weight=ft.FontWeight.BOLD),
                ft.Text(strings_es.EXPORT_SUBTITLE, color=ft.Colors.GREY_700, size=13),
                ft.Row(
                    [date_from_field, date_to_field, export_button],
                    spacing=12,
                    wrap=True,
                    run_spacing=8,
                ),
                status_text,
            ],
            spacing=12,
            expand=True,
        ),
    )
