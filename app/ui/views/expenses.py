"""Expenses screen — create plain expenses, edit (new version), void (soft
delete) with a confirmation dialog, and a "linked to restock" badge for
expenses that a restock batch pays for.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.db.repositories import batches as batches_repo
from app.db.repositories import expenses as expenses_repo
from app.domain.balance import format_cents
from app.ui import strings_es
from app.ui.components.payment_split import PaymentSplit
from app.ui.session import Session
from app.ui.views import expenses_controller
from app.ui.views.common_controller import (
    format_payment_breakdown,
    format_timestamp,
    payment_split_status,
)


def build(
    conn,
    session: Session,
    on_change: Callable[[], None],
    page: ft.Page | None = None,
) -> ft.Control:
    editing_logical_id: int | None = None

    def _update() -> None:
        if page is not None:
            page.update()

    description_field = ft.TextField(label=strings_es.EXPENSES_DESCRIPTION_LABEL, expand=True)
    payment_split = PaymentSplit(
        cash_label=strings_es.EXPENSES_CASH_LABEL,
        qr_label=strings_es.EXPENSES_QR_LABEL,
        message_builder=payment_split_status,
        field_width=140,
    )
    payment_hint = ft.Text(strings_es.EXPENSES_CASH_QR_HINT, color=ft.Colors.GREY_600, size=12)
    submit_button = ft.Button(strings_es.EXPENSES_CREATE_BUTTON)
    status_text = ft.Text("", color=ft.Colors.RED_700)
    expenses_list = ft.Column(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)

    def _list() -> None:
        rows = expenses_repo.list_current_expenses(conn, limit=100)
        if not rows:
            expenses_list.controls = [
                ft.Text(strings_es.EXPENSES_EMPTY_LIST, color=ft.Colors.GREY_600)
            ]
        else:
            expenses_list.controls = [_build_expense_row(r) for r in rows]
        _update()

    def _build_expense_row(row) -> ft.Control:
        logical_id = int(row["logical_id"])
        linked_to_batch = batches_repo.find_batch_for_expense(conn, logical_id) is not None
        breakdown = format_payment_breakdown(
            [dict(p) for p in expenses_repo.get_expense_payments(conn, int(row["id"]))]
        )
        badge = ft.Container(
            content=ft.Text(
                strings_es.EXPENSES_BADGE_LINKED,
                color=ft.Colors.WHITE,
                size=11,
            ),
            bgcolor=ft.Colors.BLUE_700,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            border_radius=6,
            visible=linked_to_batch,
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [ft.Text(row["description"], weight=ft.FontWeight.BOLD), badge],
                                spacing=8,
                            ),
                            ft.Text(
                                f"{format_timestamp(int(row['timestamp']))}  •  {row['user_name']}  •  {breakdown}",
                                color=ft.Colors.GREY_700,
                                size=12,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Text(f"$ {format_cents(int(row['amount']))}", width=100),
                    ft.OutlinedButton(
                        strings_es.EXPENSES_EDIT_BUTTON,
                        on_click=lambda e, r=row: _open_edit(r),
                    ),
                    ft.OutlinedButton(
                        strings_es.EXPENSES_VOID_BUTTON,
                        on_click=lambda e, r=row: _confirm_void(r),
                    ),
                ],
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
            border_radius=8,
        )

    def _on_submit(e) -> None:
        error = expenses_controller.create_form_error(
            description_field.value, payment_split.cash_text, payment_split.qr_text
        )
        if error is not None:
            status_text.value = error
            status_text.color = ft.Colors.RED_700
            _update()
            return
        payments = expenses_controller.build_payments(
            payment_split.cash_text, payment_split.qr_text
        )
        assert payments is not None
        nonlocal editing_logical_id
        if editing_logical_id is not None:
            expenses_repo.edit_expense(
                conn,
                editing_logical_id,
                (description_field.value or "").strip(),
                payments,
                session.user_id,
            )
            status_text.value = strings_es.EXPENSES_SUCCESS_EDITED
            editing_logical_id = None
            submit_button.text = strings_es.EXPENSES_CREATE_BUTTON
        else:
            expenses_repo.create_expense(
                conn, (description_field.value or "").strip(), payments, session.user_id
            )
            status_text.value = strings_es.EXPENSES_SUCCESS_CREATED
        status_text.color = ft.Colors.GREEN_700
        description_field.value = ""
        payment_split.clear()
        _list()
        on_change()

    def _open_edit(row) -> None:
        nonlocal editing_logical_id
        editing_logical_id = int(row["logical_id"])
        description_field.value = row["description"]
        cash_cents = None
        qr_cents = None
        for payment in expenses_repo.get_expense_payments(conn, int(row["id"])):
            if payment["method"] == "cash":
                cash_cents = int(payment["amount"])
            else:
                qr_cents = int(payment["amount"])
        payment_split.set_values(cash_cents, qr_cents)
        submit_button.text = strings_es.EXPENSES_EDIT_MODE.format(logical_id=editing_logical_id)
        status_text.value = ""
        _update()

    def _confirm_void(row) -> None:
        logical_id = int(row["logical_id"])
        linked_to_batch = batches_repo.find_batch_for_expense(conn, logical_id) is not None
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(strings_es.EXPENSES_VOID_TITLE),
            content=ft.Text(expenses_controller.void_warning(linked_to_batch)),
            actions=[
                ft.TextButton(strings_es.COMMON_CANCEL, on_click=lambda e: _close(dialog)),
                ft.TextButton(
                    strings_es.EXPENSES_VOID_CONFIRM,
                    on_click=lambda e: _void(logical_id, dialog),
                ),
            ],
        )

        def _void(expense_logical_id: int, dlg) -> None:
            expenses_repo.void_expense(conn, expense_logical_id, session.user_id)
            _close(dlg)
            status_text.value = strings_es.EXPENSES_SUCCESS_VOIDED
            status_text.color = ft.Colors.GREEN_700
            _list()
            on_change()

        def _close(dlg) -> None:
            if page is not None:
                page.pop_dialog()
            _update()

        if page is not None:
            page.show_dialog(dialog)

    submit_button.on_click = _on_submit
    _list()

    return ft.Container(
        padding=16,
        content=ft.Column(
            [
                ft.Text(strings_es.EXPENSES_TITLE, size=20, weight=ft.FontWeight.BOLD),
                ft.Row([description_field, payment_split.control, submit_button], spacing=10),
                payment_hint,
                status_text,
                ft.Divider(height=8),
                ft.Text(strings_es.EXPENSES_RECENT_TITLE, weight=ft.FontWeight.BOLD),
                ft.Container(content=expenses_list, padding=4, expand=True),
            ],
            spacing=10,
            expand=True,
        ),
    )
