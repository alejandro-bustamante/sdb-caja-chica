"""Cash count ("arqueo") screen — record a snapshot of counted cash against
the computed expected amount, showing the difference prominently. History is
read-only: a cash count is a snapshot, never retroactively corrected.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.db.repositories import cash_counts as cash_counts_repo
from app.domain.balance import compute_expected_cash, format_cents
from app.ui import strings_es
from app.ui.session import Session
from app.ui.views import cash_counts_controller
from app.ui.views.common_controller import format_timestamp


def build(
    conn,
    session: Session,
    on_change: Callable[[], None],
    page: ft.Page | None = None,
) -> ft.Control:
    def _update() -> None:
        if page is not None:
            page.update()

    counted_field = ft.TextField(
        label=strings_es.ARQUEO_COUNTED_LABEL, keyboard_type=ft.KeyboardType.NUMBER, width=220
    )
    note_field = ft.TextField(label=strings_es.ARQUEO_NOTE_LABEL, expand=True)
    record_button = ft.Button(strings_es.ARQUEO_RECORD_BUTTON)
    status_text = ft.Text("", color=ft.Colors.RED_700)
    result_text = ft.Text(
        "",
        size=22,
        weight=ft.FontWeight.BOLD,
        visible=False,
    )
    history_list = ft.Column(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)

    def _on_record(e) -> None:
        counted = cash_counts_controller.parse_counted(counted_field.value)
        error = cash_counts_controller.counted_cash_error(counted_field.value)
        if error is not None:
            status_text.value = error
            status_text.color = ft.Colors.RED_700
            result_text.visible = False
            _update()
            return
        assert counted is not None
        expected = compute_expected_cash(conn)
        cash_counts_repo.record_cash_count(
            conn, counted, session.user_id, (note_field.value or "").strip() or None
        )
        result_text.value = cash_counts_controller.result_message(counted, expected)
        if counted == expected:
            result_text.color = ft.Colors.GREEN_700
        else:
            result_text.color = ft.Colors.RED_700 if counted < expected else ft.Colors.AMBER_700
        result_text.visible = True
        status_text.value = ""
        counted_field.value = ""
        note_field.value = ""
        reload_history()
        on_change()

    def _build_history_row(row) -> ft.Control:
        difference = int(row["difference"])
        diff_text = (
            f"+$ {format_cents(difference)}"
            if difference >= 0
            else f"- $ {format_cents(-difference)}"
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(format_timestamp(int(row["timestamp"])), width=120),
                    ft.Text(row["user_name"], width=100),
                    ft.Text(f"$ {format_cents(int(row['counted_cash']))}", width=100),
                    ft.Text(f"$ {format_cents(int(row['expected_cash']))}", width=100),
                    ft.Text(diff_text, width=100, weight=ft.FontWeight.BOLD),
                    ft.Text(row["note"] or "", expand=True, color=ft.Colors.GREY_700),
                ],
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
            border_radius=8,
        )

    def reload_history() -> None:
        rows = cash_counts_repo.list_cash_counts(conn, limit=50)
        if not rows:
            history_list.controls = [
                ft.Text(strings_es.ARQUEO_EMPTY_HISTORY, color=ft.Colors.GREY_600)
            ]
        else:
            header = ft.Row(
                [
                    ft.Text(strings_es.ARQUEO_DATE_COL, width=120, weight=ft.FontWeight.BOLD),
                    ft.Text(strings_es.ARQUEO_USER_COL, width=100, weight=ft.FontWeight.BOLD),
                    ft.Text(strings_es.ARQUEO_COUNTED_COL, width=100, weight=ft.FontWeight.BOLD),
                    ft.Text(strings_es.ARQUEO_EXPECTED_COL, width=100, weight=ft.FontWeight.BOLD),
                    ft.Text(strings_es.ARQUEO_DIFF_LABEL, width=100, weight=ft.FontWeight.BOLD),
                    ft.Text(strings_es.ARQUEO_NOTE_COL, expand=True, weight=ft.FontWeight.BOLD),
                ],
                spacing=10,
            )
            history_list.controls = [header] + [_build_history_row(r) for r in rows]
        _update()

    record_button.on_click = _on_record
    reload_history()

    return ft.Container(
        padding=16,
        content=ft.Column(
            [
                ft.Text(strings_es.ARQUEO_TITLE, size=20, weight=ft.FontWeight.BOLD),
                ft.Row([counted_field, note_field, record_button], spacing=10),
                status_text,
                result_text,
                ft.Divider(height=8),
                ft.Text(strings_es.ARQUEO_HISTORY_TITLE, weight=ft.FontWeight.BOLD),
                ft.Container(content=history_list, padding=4, expand=True),
            ],
            spacing=10,
            expand=True,
        ),
    )
