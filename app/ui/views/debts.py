"""Debts ("fiado") screen — one-click mark-as-paid, partial payments (abono),
and a read-only settled-debts toggle.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.db.repositories import debts as debts_repo
from app.db.repositories import sales as sales_repo
from app.domain.balance import format_cents
from app.domain.validation import ValidationError
from app.ui import strings_es
from app.ui.session import Session
from app.ui.views import debts_controller


def build(
    conn,
    session: Session,
    on_change: Callable[[], None],
    page: ft.Page | None = None,
) -> ft.Control:
    read_only = session.read_only

    def _update() -> None:
        if page is not None:
            page.update()

    show_settled = ft.Switch(label=strings_es.DEBTS_SHOW_SETTLED, value=False)
    status_text = ft.Text("", color=ft.Colors.RED_700)
    open_list = ft.Column(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)
    settled_list = ft.Column(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)

    def _customer_note(logical_id: int) -> str:
        sale = sales_repo.get_sale_current(conn, logical_id)
        return (sale["customer_note"] or "") if sale is not None else ""

    def _header_row() -> ft.Control:
        header_controls: list[ft.Control] = [
            ft.Text(strings_es.DEBTS_COL_CUSTOMER, width=140, weight=ft.FontWeight.BOLD),
            ft.Text(strings_es.DEBTS_COL_NOTE, width=220, weight=ft.FontWeight.BOLD),
            ft.Text(strings_es.DEBTS_COL_TOTAL, width=90, weight=ft.FontWeight.BOLD),
            ft.Text(strings_es.DEBTS_COL_PAID, width=90, weight=ft.FontWeight.BOLD),
            ft.Text(strings_es.DEBTS_COL_OUTSTANDING, width=100, weight=ft.FontWeight.BOLD),
        ]
        if not read_only:
            # Spacer column aligning with the mark-paid/abono actions.
            header_controls.append(ft.Text("", width=220))
        # Wrapped so a narrow window reflows columns instead of clipping the
        # last one (the fixed-width cells must not use expand=True: expanding
        # children break wrapped rows).
        return ft.Row(header_controls, spacing=8, wrap=True, run_spacing=6)

    def _mark_paid(logical_id: int) -> None:
        try:
            debts_repo.mark_debt_paid(conn, logical_id, session.user_id)
        except ValidationError as exc:
            status_text.value = strings_es.DEBTS_WRITE_ERROR.format(message=exc)
            status_text.color = ft.Colors.RED_700
            _update()
            return
        _set_success(strings_es.DEBTS_SUCCESS_PAID)
        reload()
        on_change()

    def _record_abono(logical_id: int, amount_field: ft.TextField, outstanding: int, err_field: ft.Text) -> None:
        error = debts_controller.abono_error(amount_field.value, outstanding)
        if error is not None:
            err_field.value = error
            _update()
            return
        amount = debts_controller.parse_abono_amount(amount_field.value)
        assert amount is not None
        try:
            debts_repo.record_partial_payment(
                conn, logical_id, amount, session.user_id
            )
        except ValidationError as exc:
            err_field.value = strings_es.DEBTS_WRITE_ERROR.format(message=exc)
            _update()
            return
        _set_success(strings_es.DEBTS_SUCCESS_ABONO)
        reload()
        on_change()

    def _set_success(message: str) -> None:
        status_text.value = message
        status_text.color = ft.Colors.GREEN_700

    def _build_open_row(debt) -> ft.Control:
        logical_id = debt.logical_id
        note = _customer_note(logical_id)
        amount_field = ft.TextField(
            label=strings_es.DEBTS_ABONO_LABEL,
            keyboard_type=ft.KeyboardType.NUMBER,
            width=160,
        )
        error_field = ft.Text("", color=ft.Colors.RED_700)
        abono_row = ft.Row(
            [
                amount_field,
                ft.Button(
                    strings_es.DEBTS_ABONO_BUTTON,
                    on_click=lambda e: _record_abono(
                        logical_id, amount_field, debt.outstanding, error_field
                    ),
                ),
                error_field,
            ],
            spacing=8,
            visible=False,
        )
        row_controls: list[ft.Control] = [
            ft.Text(debt.customer_name or "?", width=140),
            ft.Text(note, width=220, color=ft.Colors.GREY_700),
            ft.Text(f"$ {format_cents(debt.total)}", width=90),
            ft.Text(f"$ {format_cents(debt.paid)}", width=90),
            ft.Text(
                f"$ {format_cents(debt.outstanding)}",
                width=100,
                weight=ft.FontWeight.BOLD,
            ),
        ]
        children: list[ft.Control] = []
        if not read_only:
            # The one-click mark-as-paid and the abono flow are write actions
            # and are not mounted while browsing an archived ledger (plan-04
            # Task 3); the row itself (customer, note, totals) stays visible.
            expand_button = ft.TextButton(
                strings_es.DEBTS_ABONO_LINK,
                on_click=lambda e: _toggle_abono(abono_row),
            )
            row_controls += [
                ft.Button(
                    strings_es.DEBTS_MARK_PAID,
                    on_click=lambda e, lid=logical_id: _mark_paid(lid),
                ),
                expand_button,
            ]
            children.append(abono_row)
        children.insert(
            0, ft.Row(row_controls, spacing=8, wrap=True, run_spacing=6)
        )
        return ft.Container(
            content=ft.Column(children, spacing=4),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
            border_radius=8,
        )

    def _toggle_abono(abono_row: ft.Row) -> None:
        abono_row.visible = not abono_row.visible
        _update()

    def _build_settled_row(debt) -> ft.Control:
        note = _customer_note(debt.logical_id)
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(debt.customer_name or "?", width=140),
                    ft.Text(note, width=220, color=ft.Colors.GREY_700),
                    ft.Text(f"$ {format_cents(debt.total)}", width=90),
                    ft.Text(f"$ {format_cents(debt.paid)}", width=90),
                    ft.Text("$ 0.00", width=100, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
                wrap=True,
                run_spacing=6,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
            border_radius=8,
        )

    def reload() -> None:
        open_rows = debts_repo.list_open_debts(conn)
        if not open_rows:
            open_list.controls = [
                ft.Text(strings_es.DEBTS_EMPTY_OPEN, color=ft.Colors.GREY_600)
            ]
        else:
            open_list.controls = [_header_row()] + [
                _build_open_row(d) for d in open_rows
            ]
        settled_rows = debts_repo.list_settled_debts(conn, limit=50)
        if show_settled.value:
            if not settled_rows:
                settled_list.controls = [
                    ft.Text(strings_es.DEBTS_EMPTY_SETTLED, color=ft.Colors.GREY_600)
                ]
            else:
                settled_list.controls = [_header_row()] + [
                    _build_settled_row(d) for d in settled_rows
                ]
        else:
            settled_list.controls = []
        _update()

    settled_panel = ft.Column(
        [
            ft.Text(strings_es.DEBTS_SETTLED_TITLE, weight=ft.FontWeight.BOLD),
            settled_list,
        ],
        spacing=8,
        visible=False,
    )

    def _build_bank_toggler(e) -> None:
        settled_panel.visible = show_settled.value
        reload()

    show_settled.on_change = _build_bank_toggler

    reload()

    return ft.Container(
        padding=16,
        content=ft.Column(
            [
                ft.Text(strings_es.DEBTS_TITLE, size=20, weight=ft.FontWeight.BOLD),
                show_settled,
                status_text,
                ft.Text(strings_es.DEBTS_OPEN_TITLE, weight=ft.FontWeight.BOLD),
                ft.Container(content=open_list, padding=4, expand=True),
                settled_panel,
            ],
            spacing=10,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
    )
