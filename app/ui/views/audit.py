"""Auditoría screen (plan-05 Task 3) — a strictly read-only audit trail.

Filter bar: time preset ("Últimas 24 horas" by default so the screen never
opens by fetching a long ledger's whole history), user (active and inactive —
an inactive user may still have made changes worth auditing), category
multi-select, and change-type multi-select. Changing any filter re-queries via
``domain.audit`` and resets pagination to the first page. Results are newest
first, one row per event, with a "Cargar más" pager and an "Exportar esta
vista" button that mirrors the currently active filters (plan-05 Task 5.2).

This screen has NO create/edit/void/mark-paid controls of any kind — not
hidden-when-read-only like plan-04's ``session.read_only`` screens, but
structurally absent, because auditing is never a write path in any session.
It therefore builds identically against a live ledger and an archived
(read-only) one; ``session`` is only read for display purposes.

The "Todas"/"Todos" chips are a select-all shortcut: clicking one selects
every category/type. An empty selection means "no restriction" (equivalent to
all), so the shortcut chip stays highlighted whenever nothing or everything
is selected.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import flet as ft

from app.db.repositories import users as users_repo
from app.domain import audit
from app.services import excel_export
from app.ui import strings_es
from app.ui.session import Session
from app.ui.views import audit_controller
from app.ui.views.common_controller import format_timestamp

PAGE_SIZE = 50

_CATEGORY_CHIP_ORDER = ["todas", *audit.ALL_CATEGORIES]
_CHANGE_TYPE_CHIP_ORDER = ["todos", *audit.ALL_CHANGE_TYPES]
_TIME_PRESET_ORDER = ["1h", "24h", "7d", "30d", audit.TIME_PRESET_ALL]

_CHANGE_TYPE_COLORS = {
    audit.CHANGE_REGISTRO: ft.Colors.GREY_700,
    audit.CHANGE_EDICION: ft.Colors.AMBER_700,
    audit.CHANGE_ELIMINACION: ft.Colors.RED_700,
}


def build(
    conn,
    session: Session,
    on_change: Callable[[], None],
    page: ft.Page | None = None,
) -> ft.Control:
    def _update() -> None:
        if page is not None:
            page.update()

    # --- Filter state --------------------------------------------------------

    selected_categories: set[str] = set()  # empty = all
    selected_types: set[str] = set()  # empty = all
    loaded: list[audit.AuditEvent] = []
    total_count = 0

    def _categories_filter() -> tuple[str, ...] | None:
        if not selected_categories or len(selected_categories) == len(
            audit.ALL_CATEGORIES
        ):
            return None
        return tuple(sorted(selected_categories))

    def _types_filter() -> tuple[str, ...] | None:
        if not selected_types or len(selected_types) == len(audit.ALL_CHANGE_TYPES):
            return None
        return tuple(sorted(selected_types))

    def _current_filters() -> audit.AuditFilters:
        preset = time_dropdown.value or audit_controller.default_time_preset()
        user_value = user_dropdown.value
        return audit.AuditFilters(
            since=audit.preset_since(preset),
            user_id=int(user_value) if user_value else None,
            categories=_categories_filter(),
            change_types=_types_filter(),
        )

    # --- Widgets -------------------------------------------------------------

    time_dropdown = ft.Dropdown(
        label=strings_es.AUDIT_FILTER_TIME,
        width=180,
        options=[
            ft.DropdownOption(key=key, text=audit_controller.time_preset_label(key))
            for key in _TIME_PRESET_ORDER
        ],
        value=audit_controller.default_time_preset(),
    )

    user_dropdown = ft.Dropdown(
        label=strings_es.AUDIT_FILTER_USER,
        width=180,
        options=[
            ft.DropdownOption(key="", text=strings_es.AUDIT_FILTER_ALL_USERS),
            *[
                ft.DropdownOption(key=str(u.id), text=u.name)
                for u in users_repo.list_all_users(conn)
            ],
        ],
        value="",
    )

    category_chips: dict[str, ft.Chip] = {}
    change_type_chips: dict[str, ft.Chip] = {}

    def _reconcile_chips() -> None:
        all_cats = len(selected_categories) in (0, len(audit.ALL_CATEGORIES))
        all_types = len(selected_types) in (0, len(audit.ALL_CHANGE_TYPES))
        for key, chip in category_chips.items():
            chip.selected = key == "todas" and all_cats or key in selected_categories
        for key, chip in change_type_chips.items():
            chip.selected = key == "todos" and all_types or key in selected_types

    def _toggle_category(key: str) -> None:
        if key == "todas":
            selected_categories.update(audit.ALL_CATEGORIES)
        elif key in selected_categories:
            selected_categories.discard(key)
        else:
            selected_categories.add(key)
        _reconcile_chips()
        _requery()

    def _toggle_change_type(key: str) -> None:
        if key == "todos":
            selected_types.update(audit.ALL_CHANGE_TYPES)
        elif key in selected_types:
            selected_types.discard(key)
        else:
            selected_types.add(key)
        _reconcile_chips()
        _requery()

    def _make_chips(
        order: list[str],
        label_of: Callable[[str], str],
        toggle: Callable[[str], None],
    ) -> list[ft.Chip]:
        chips: list[ft.Chip] = []
        for key in order:
            chip = ft.Chip(
                label=ft.Text(label_of(key)),
                selected=False,
                on_click=lambda e, k=key: toggle(k),
            )
            chips.append(chip)
        return chips

    def _category_chip_label(key: str) -> str:
        if key == "todas":
            return strings_es.AUDIT_FILTER_ALL_CATEGORIES
        return audit_controller.category_label(key)

    def _change_type_chip_label(key: str) -> str:
        if key == "todos":
            return strings_es.AUDIT_FILTER_ALL_TYPES
        return audit_controller.change_type_label(key)

    category_chips = {
        key: chip
        for key, chip in zip(
            _CATEGORY_CHIP_ORDER,
            _make_chips(
                _CATEGORY_CHIP_ORDER, _category_chip_label, _toggle_category
            ),
            strict=True,
        )
    }
    change_type_chips = {
        key: chip
        for key, chip in zip(
            _CHANGE_TYPE_CHIP_ORDER,
            _make_chips(
                _CHANGE_TYPE_CHIP_ORDER,
                _change_type_chip_label,
                _toggle_change_type,
            ),
            strict=True,
        )
    }

    count_text = ft.Text("", color=ft.Colors.GREY_700, size=13)
    status_text = ft.Text("", color=ft.Colors.RED_700)
    events_list = ft.Column(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)
    load_more_button = ft.OutlinedButton(strings_es.AUDIT_LOAD_MORE)
    export_button = ft.OutlinedButton(
        strings_es.AUDIT_EXPORT_BUTTON, icon=ft.Icons.FILE_DOWNLOAD
    )

    # --- Row rendering -------------------------------------------------------

    def _badge(text: str, color) -> ft.Control:
        return ft.Container(
            content=ft.Text(text, color=ft.Colors.WHITE, size=11),
            bgcolor=color,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            border_radius=6,
        )

    def _build_row(event: audit.AuditEvent) -> ft.Control:
        summary = audit_controller.summary_for(event)
        detail_column = ft.Column(spacing=4, visible=False)
        detail_button = ft.TextButton(strings_es.AUDIT_DETAIL_BUTTON)

        def _toggle_detail(e) -> None:
            detail_column.visible = not detail_column.visible
            detail_button.text = (
                strings_es.AUDIT_DETAIL_HIDE
                if detail_column.visible
                else strings_es.AUDIT_DETAIL_BUTTON
            )
            _update()

        if audit_controller.detail_available(event):
            detail_button.on_click = _toggle_detail
            detail_column.controls = [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(line, color=ft.Colors.GREY_800, size=12)
                            for line in audit_controller.detail_lines(conn, event)
                        ],
                        spacing=2,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                    bgcolor=ft.Colors.GREY_100,
                    border_radius=6,
                )
            ]

        row_controls: list[ft.Control] = [
            ft.Text(format_timestamp(event.timestamp), width=88, size=12),
            _badge(
                audit_controller.category_label(event.category),
                ft.Colors.BLUE_GREY_700,
            ),
            _badge(
                audit_controller.change_type_label(event.change_type),
                _CHANGE_TYPE_COLORS[event.change_type],
            ),
            ft.Text(event.user_name, width=80, size=12),
            ft.Text(summary, expand=True, size=13),
        ]
        if audit_controller.detail_available(event):
            row_controls.append(detail_button)
        header = ft.Row(row_controls, spacing=8)
        return ft.Container(
            content=ft.Column([header, detail_column], spacing=4),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
            border_radius=8,
        )

    # --- Query + render ------------------------------------------------------

    def _requery() -> None:
        nonlocal loaded, total_count
        filters = _current_filters()
        loaded = audit.list_audit_events(
            conn,
            since=filters.since,
            user_id=filters.user_id,
            categories=filters.categories,
            change_types=filters.change_types,
            limit=PAGE_SIZE,
            offset=0,
        )
        total_count = audit.count_audit_events(
            conn,
            since=filters.since,
            user_id=filters.user_id,
            categories=filters.categories,
            change_types=filters.change_types,
        )
        _render()

    def _render() -> None:
        count_text.value = strings_es.AUDIT_RESULTS_COUNT.format(count=total_count)
        if not loaded:
            events_list.controls = [
                ft.Text(strings_es.AUDIT_EMPTY, color=ft.Colors.GREY_600)
            ]
            load_more_button.visible = False
        else:
            events_list.controls = [_build_row(e) for e in loaded]
            load_more_button.visible = len(loaded) < total_count
        _update()

    def _load_more(e) -> None:
        nonlocal loaded
        filters = _current_filters()
        more = audit.list_audit_events(
            conn,
            since=filters.since,
            user_id=filters.user_id,
            categories=filters.categories,
            change_types=filters.change_types,
            limit=PAGE_SIZE,
            offset=len(loaded),
        )
        if not more:
            return
        loaded.extend(more)
        events_list.controls.extend(_build_row(e) for e in more)
        load_more_button.visible = len(loaded) < total_count
        _update()

    async def _on_export(e) -> None:
        picker = ft.FilePicker()
        path = await picker.save_file(
            dialog_title=strings_es.AUDIT_EXPORT_BUTTON,
            file_name=audit_controller.default_file_name(),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )
        if not path:
            return
        try:
            excel_export.export_audit_events(conn, _current_filters(), Path(path))
            status_text.value = strings_es.EXPORT_SUCCESS.format(path=path)
            status_text.color = ft.Colors.GREEN_700
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            status_text.value = strings_es.EXPORT_ERROR.format(message=exc)
            status_text.color = ft.Colors.RED_700
        _update()

    time_dropdown.on_change = lambda e: _requery()
    user_dropdown.on_change = lambda e: _requery()
    load_more_button.on_click = _load_more
    export_button.on_click = _on_export

    _reconcile_chips()
    _requery()

    filter_bar = ft.Column(
        [
            ft.Row(
                [time_dropdown, user_dropdown, export_button],
                spacing=12,
                wrap=True,
            ),
            ft.Row(
                [
                    ft.Text(
                        strings_es.AUDIT_FILTER_CATEGORY, color=ft.Colors.GREY_700
                    ),
                    *category_chips.values(),
                ],
                spacing=6,
                wrap=True,
            ),
            ft.Row(
                [
                    ft.Text(
                        strings_es.AUDIT_FILTER_CHANGE_TYPE,
                        color=ft.Colors.GREY_700,
                    ),
                    *change_type_chips.values(),
                ],
                spacing=6,
                wrap=True,
            ),
        ],
        spacing=8,
    )

    return ft.Container(
        padding=16,
        content=ft.Column(
            [
                ft.Text(strings_es.AUDIT_TITLE, size=20, weight=ft.FontWeight.BOLD),
                ft.Text(strings_es.AUDIT_SUBTITLE, color=ft.Colors.GREY_700, size=13),
                filter_bar,
                status_text,
                count_text,
                ft.Divider(height=8),
                ft.Container(content=events_list, padding=4, expand=True),
                ft.Container(
                    content=ft.Row([load_more_button], alignment=ft.MainAxisAlignment.CENTER),
                    visible=True,
                ),
            ],
            spacing=10,
            expand=True,
        ),
    )
