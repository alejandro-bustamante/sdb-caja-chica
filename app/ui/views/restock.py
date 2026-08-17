"""Restock screen — record a batch: repeatable product+quantity lines, one
optional batch expense (which becomes a linked expenses row), recent batches.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.db.repositories import batches as batches_repo
from app.db.repositories import expenses as expenses_repo
from app.db.repositories import products as products_repo
from app.ui import strings_es
from app.ui.components.payment_split import PaymentSplit
from app.ui.session import Session
from app.ui.views import restock_controller
from app.ui.views.common_controller import (
    format_items_summary,
    format_payment_breakdown,
    format_timestamp,
    parse_quantity_input,
)


def build(
    conn,
    session: Session,
    on_change: Callable[[], None],
    page: ft.Page | None = None,
) -> ft.Control:
    read_only = session.read_only
    lines: list[tuple[int, str, int]] = []  # (product_id, product_name, quantity)

    def _update() -> None:
        if page is not None:
            page.update()

    products = products_repo.list_active_products(conn)
    products_by_id = {p.id: p for p in products}

    product_dropdown = ft.Dropdown(
        label=strings_es.RESTOCK_PRODUCT_LABEL,
        options=[
            ft.dropdown.Option(key=str(p.id), text=p.name)
            for p in sorted(products, key=lambda p: p.name)
        ],
        expand=True,
    )
    quantity_field = ft.TextField(
        label=strings_es.RESTOCK_QUANTITY_LABEL,
        value="1",
        keyboard_type=ft.KeyboardType.NUMBER,
        width=110,
    )
    add_button = ft.Button(strings_es.RESTOCK_ADD_BUTTON)
    expense_split = PaymentSplit(
        cash_label=strings_es.RESTOCK_EXPENSE_CASH_LABEL,
        qr_label=strings_es.RESTOCK_EXPENSE_QR_LABEL,
        message_builder=restock_controller.payment_status_message,
        field_width=170,
    )
    expense_desc_field = ft.TextField(label=strings_es.RESTOCK_EXPENSE_DESC_LABEL)
    expense_hint = ft.Text(
        strings_es.RESTOCK_PAYMENT_HINT, color=ft.Colors.GREY_600, size=12
    )
    submit_button = ft.Button(strings_es.RESTOCK_SUBMIT_BUTTON, width=240)
    status_text = ft.Text("", color=ft.Colors.RED_700)

    lines_list = ft.Column(spacing=4, expand=True, scroll=ft.ScrollMode.AUTO)

    def _list_lines() -> None:
        if not lines:
            lines_list.controls = [
                ft.Text(strings_es.RESTOCK_EMPTY_ITEMS, color=ft.Colors.GREY_600)
            ]
        else:
            lines_list.controls = [
                ft.Row(
                    [
                        ft.Text(restock_controller.line_summary(name, qty), expand=True),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip=strings_es.SALES_REMOVE_LINE_BUTTON,
                            on_click=lambda e, i=index: _remove_line(i),
                        ),
                    ],
                    spacing=8,
                )
                for index, (_, name, qty) in enumerate(lines)
            ]
        _update()

    def _add_line(e) -> None:
        key = product_dropdown.value
        product = products_by_id.get(int(key)) if key else None
        quantity = parse_quantity_input(quantity_field.value)
        error = restock_controller.add_line_error(
            product.id if product else None, quantity_field.value
        )
        if error is not None:
            status_text.value = error
            status_text.color = ft.Colors.RED_700
            _update()
            return
        assert product is not None and quantity is not None
        lines.append((product.id, product.name, quantity))
        quantity_field.value = "1"
        product_dropdown.value = None
        status_text.value = ""
        _list_lines()

    def _remove_line(index: int) -> None:
        del lines[index]
        _list_lines()

    def _submit(e) -> None:
        if not lines:
            status_text.value = strings_es.RESTOCK_EMPTY_ITEMS
            status_text.color = ft.Colors.RED_700
            _update()
            return
        expense_error = restock_controller.expense_payments_error(
            expense_split.cash_text, expense_split.qr_text
        )
        if expense_error is not None:
            status_text.value = expense_error
            status_text.color = ft.Colors.RED_700
            _update()
            return
        expense_payments = restock_controller.build_expense_payments(
            expense_split.cash_text, expense_split.qr_text
        )
        assert expense_payments is not None
        try:
            batches_repo.create_batch(
                conn,
                [(pid, qty) for pid, _, qty in lines],
                expense_payments,
                (expense_desc_field.value or "").strip() or None,
                session.user_id,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            status_text.value = strings_es.RESTOCK_WRITE_ERROR.format(message=exc)
            status_text.color = ft.Colors.RED_700
            _update()
            return
        lines.clear()
        expense_split.clear()
        expense_desc_field.value = ""
        status_text.value = strings_es.RESTOCK_SUCCESS
        status_text.color = ft.Colors.GREEN_700
        _list_lines()
        reload_recent()
        on_change()

    def _build_recent_row(row) -> ft.Control:
        items = [dict(i) for i in batches_repo.get_batch_items(conn, int(row["id"]))]
        summary = format_items_summary(items)
        expense_display = strings_es.RESTOCK_NO_EXPENSE
        if row["expense_logical_id"] is not None:
            expense_row = batches_repo.resolve_batch_expense(
                conn, int(row["expense_logical_id"])
            )
            if expense_row is None and batches_repo.is_batch_expense_deleted(
                conn, int(row["expense_logical_id"])
            ):
                expense_display = strings_es.RESTOCK_EXPENSE_DELETED
            elif expense_row is not None:
                breakdown = format_payment_breakdown(
                    [
                        dict(p)
                        for p in expenses_repo.get_expense_payments(
                            conn, int(expense_row["id"])
                        )
                    ]
                )
                expense_display = strings_es.RESTOCK_LINKED_EXPENSE.format(
                    description=expense_row["description"],
                    breakdown=breakdown,
                )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        f"{format_timestamp(int(row['timestamp']))}  •  {summary}",
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(expense_display, color=ft.Colors.GREY_700),
                ],
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
            border_radius=8,
            margin=ft.Margin.symmetric(vertical=4),
        )

    def reload_recent() -> None:
        rows = batches_repo.list_recent_batches(conn, limit=50)
        if not rows:
            recent_list.controls = [
                ft.Text(strings_es.RESTOCK_EMPTY_RECENT, color=ft.Colors.GREY_600)
            ]
        else:
            recent_list.controls = [_build_recent_row(r) for r in rows]
        _update()

    recent_list = ft.Column(spacing=2, expand=True, scroll=ft.ScrollMode.AUTO)

    add_button.on_click = _add_line
    submit_button.on_click = _submit

    form = ft.Container(
        content=ft.Column(
            [
                ft.Text(strings_es.RESTOCK_TITLE, size=20, weight=ft.FontWeight.BOLD),
                ft.Row([product_dropdown, quantity_field, add_button], spacing=12),
                ft.Text(strings_es.RESTOCK_ITEMS_TITLE, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=lines_list,
                    border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
                    border_radius=8,
                    padding=8,
                    height=160,
                ),
                expense_split.control,
                expense_desc_field,
                expense_hint,
                submit_button,
                status_text,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=16,
        width=560,
        expand=True,
    )

    recent_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text(strings_es.RESTOCK_RECENT_TITLE, size=20, weight=ft.FontWeight.BOLD),
                recent_list,
            ],
            spacing=10,
            expand=True,
        ),
        padding=16,
        width=520,
        expand=True,
    )

    _list_lines()
    reload_recent()

    if read_only:
        # Browse-only mode (plan-04 Task 3): the whole entry form — lines,
        # expense split, submit — is a write surface and is not mounted; only
        # the recent-batches list stays.
        return ft.Row([recent_panel], expand=True)
    return ft.Row([form, ft.VerticalDivider(width=1), recent_panel], expand=True)
