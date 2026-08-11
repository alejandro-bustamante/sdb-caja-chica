"""Sales entry screen — cart building, payment split, credit (fiado), and
the "ventas de hoy" list with edit/void.

All decision logic lives in ``sales_controller.py`` (no Flet); this module
only wires widgets to it.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.db.repositories import products as products_repo
from app.db.repositories import sales as sales_repo
from app.domain.balance import format_cents
from app.domain.types import SalePaymentInput
from app.domain.validation import ValidationError
from app.ui import strings_es
from app.ui.session import Session
from app.ui.views import sales_controller
from app.ui.views.common_controller import (
    format_items_summary,
    format_timestamp,
    parse_quantity_input,
    start_of_today_ts,
)


def build(
    conn,
    session: Session,
    on_change: Callable[[], None],
    page: ft.Page | None = None,
) -> ft.Control:
    cart: list[sales_controller.CartLine] = []
    editing_logical_id: int | None = None

    def _update() -> None:
        if page is not None:
            page.update()

    def _show_dialog(dlg: ft.AlertDialog) -> None:
        if page is not None:
            page.show_dialog(dlg)

    products = products_repo.list_active_products(conn)
    products_by_id = {p.id: p for p in products}

    product_dropdown = ft.Dropdown(
        label=strings_es.SALES_PRODUCT_LABEL,
        options=[
            ft.dropdown.Option(key=str(p.id), text=p.name)
            for p in sorted(products, key=lambda p: p.name)
        ],
        expand=True,
    )
    quantity_field = ft.TextField(
        label=strings_es.SALES_QUANTITY_LABEL,
        value="1",
        keyboard_type=ft.KeyboardType.NUMBER,
        width=110,
    )
    add_button = ft.Button(strings_es.SALES_ADD_BUTTON)

    cart_list = ft.Column(spacing=4, expand=True, scroll=ft.ScrollMode.AUTO)
    total_text = ft.Text("", size=18, weight=ft.FontWeight.BOLD)
    status_text = ft.Text("", color=ft.Colors.RED_700)

    credit_switch = ft.Switch(label=strings_es.SALES_CREDIT_LABEL, value=False)
    cash_field = ft.TextField(
        label=strings_es.SALES_CASH_LABEL, keyboard_type=ft.KeyboardType.NUMBER, width=170
    )
    qr_field = ft.TextField(
        label=strings_es.SALES_QR_LABEL, keyboard_type=ft.KeyboardType.NUMBER, width=170
    )
    payment_hint = ft.Text("", color=ft.Colors.AMBER_700)
    payment_row = ft.Row([cash_field, qr_field, payment_hint], spacing=12)
    customer_name_field = ft.TextField(label=strings_es.SALES_CUSTOMER_NAME_LABEL)
    customer_note_field = ft.TextField(label=strings_es.SALES_CUSTOMER_NOTE_LABEL)
    customer_fields = ft.Column([customer_name_field, customer_note_field])
    submit_button = ft.Button(strings_es.SALES_SUBMIT_BUTTON, width=240)
    edit_banner = ft.Container(
        content=ft.Row([]),
        bgcolor=ft.Colors.AMBER_100,
        padding=10,
        border_radius=8,
        visible=False,
    )
    cancel_edit_button = ft.TextButton(strings_es.SALES_CANCEL_EDIT)

    def _set_status(message: str, *, success: bool = False) -> None:
        status_text.value = message
        status_text.color = ft.Colors.GREEN_700 if success else ft.Colors.RED_700

    def redraw_cart() -> None:
        rows: list[ft.Control] = []
        for index, line in enumerate(cart):
            rows.append(
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.PRICE_CHANGE,
                            tooltip=strings_es.SALES_EDIT_LINE_BUTTON,
                            on_click=lambda e, i=index: _open_override_dialog(i),
                        ),
                        ft.Text(sales_controller.format_line_summary(line), expand=True),
                        ft.Text(
                            strings_es.SALES_OVERRIDE_BADGE,
                            color=ft.Colors.AMBER_700,
                            visible=line.overridden,
                            size=12,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip=strings_es.SALES_REMOVE_LINE_BUTTON,
                            on_click=lambda e, i=index: _remove_line(i),
                        ),
                    ],
                    spacing=8,
                )
            )
        if not rows:
            rows.append(
                ft.Text(strings_es.SALES_CART_EMPTY, color=ft.Colors.GREY_600)
            )
        cart_list.controls = rows
        total_text.value = strings_es.SALES_TOTAL_LABEL.format(
            total=format_cents(sales_controller.cart_total(cart))
        )
        _update()

    def _payment_hint() -> None:
        if credit_switch.value:
            payment_hint.value = ""
            return
        message = sales_controller.payment_status_message(
            cash_field.value, qr_field.value, sales_controller.cart_total(cart)
        )
        payment_hint.value = message or ""
        _update()

    def _toggle_credit(e) -> None:
        is_credit = credit_switch.value
        payment_row.visible = not is_credit
        customer_fields.visible = is_credit
        if not is_credit:
            customer_name_field.value = ""
            customer_note_field.value = ""
        _payment_hint()
        _update()

    def _add_line(e) -> None:
        key = product_dropdown.value
        product = products_by_id.get(int(key)) if key else None
        quantity = parse_quantity_input(quantity_field.value)
        error = sales_controller.add_line_input_error(
            product.id if product else None, quantity_field.value
        )
        if error is not None:
            _set_status(error)
            _update()
            return
        assert product is not None and quantity is not None
        sales_controller.add_cart_line(
            cart,
            product.id,
            product.name,
            quantity,
            product.current_price if product.current_price is not None else 0,
        )
        quantity_field.value = "1"
        product_dropdown.value = None
        _set_status("")
        redraw_cart()
        _payment_hint()

    def _remove_line(index: int) -> None:
        sales_controller.remove_cart_line(cart, index)
        redraw_cart()
        _payment_hint()

    def _open_override_dialog(index: int) -> None:
        price_field = ft.TextField(
            label=strings_es.SALES_OVERRIDE_HINT,
            keyboard_type=ft.KeyboardType.NUMBER,
            value=format_cents(cart[index].unit_price),
        )
        error_text = ft.Text("", color=ft.Colors.RED_700)
        dialog = ft.AlertDialog(
            title=ft.Text(strings_es.SALES_OVERRIDE_TITLE),
            content=ft.Column([price_field, error_text]),
            actions=[
                ft.TextButton(strings_es.COMMON_CANCEL, on_click=lambda e: _close(dialog)),
                ft.TextButton(strings_es.COMMON_SAVE, on_click=lambda e: _save()),
            ],
        )

        def _save() -> None:
            new_price = sales_controller.parse_money_input(price_field.value)
            if new_price is None:
                error_text.value = strings_es.SALES_INVALID_AMOUNT
                _update()
                return
            sales_controller.override_cart_line_price(cart, index, new_price)
            redraw_cart()
            _close(dialog)

        def _close(dlg) -> None:
            if page is not None:
                page.pop_dialog()
            _update()

        _show_dialog(dialog)

    def _clear_form() -> None:
        cash_field.value = ""
        qr_field.value = ""
        customer_name_field.value = ""
        customer_note_field.value = ""
        credit_switch.value = False
        customer_fields.visible = False
        payment_row.visible = True
        _payment_hint()
        redraw_cart()

    def _on_submit(e) -> None:
        nonlocal editing_logical_id
        is_credit = bool(credit_switch.value)
        customer_name = (customer_name_field.value or "").strip()
        customer_note = (customer_note_field.value or "").strip()

        if not cart:
            _set_status(strings_es.SALES_EMPTY_CART_ERROR)
            _update()
            return
        items = sales_controller.to_sale_items(cart)

        if is_credit:
            if not customer_name:
                _set_status(strings_es.SALES_NEED_CUSTOMER_NAME)
                _update()
                return
            payments: list[SalePaymentInput] = []
        else:
            built, error = sales_controller.build_payments_from_texts(
                cash_field.value, qr_field.value
            )
            if error is not None:
                _set_status(error)
                _update()
                return
            payments = built if built is not None else []

        error = sales_controller.submit_error_message(
            items, payments, is_credit, customer_name
        )
        if error is not None:
            _set_status(error)
            _update()
            return

        try:
            if editing_logical_id is not None:
                sales_repo.edit_sale(
                    conn,
                    editing_logical_id,
                    items,
                    payments,
                    is_credit,
                    customer_name or None,
                    customer_note or None,
                    session.user_id,
                )
                _set_status(strings_es.SALES_SUCCESS_EDITED, success=True)
            else:
                sales_repo.create_sale(
                    conn,
                    items,
                    payments,
                    is_credit,
                    customer_name or None,
                    customer_note or None,
                    session.user_id,
                )
                _set_status(strings_es.SALES_SUCCESS_CREATED, success=True)
        except ValidationError as exc:
            _set_status(sales_controller.translate_write_error(exc))
            _update()
            return

        editing_logical_id = None
        cart.clear()
        edit_banner.visible = False
        _clear_form()
        reload_recent()
        on_change()

    def _open_edit(index: int) -> None:
        row = recent_rows[index]
        sale = sales_repo.get_sale_current(conn, int(row["logical_id"]))
        if sale is None:
            return
        nonlocal editing_logical_id
        editing_logical_id = int(row["logical_id"])
        cart.clear()
        for item in sales_repo.get_sale_items(conn, int(row["id"])):
            cart.append(
                sales_controller.CartLine(
                    product_id=int(item["product_id"]),
                    name=item["product_name"],
                    quantity=int(item["quantity"]),
                    unit_price=int(item["unit_price_applied"]),
                    overridden=bool(item["price_manually_overridden"]),
                )
            )
        is_credit = bool(sale["is_credit"])
        credit_switch.value = is_credit
        payment_row.visible = not is_credit
        customer_fields.visible = is_credit
        cash_field.value = ""
        qr_field.value = ""
        for payment in sales_repo.get_sale_payments(conn, int(row["id"])):
            if payment["method"] == "cash":
                cash_field.value = format_cents(int(payment["amount"]))
            else:
                qr_field.value = format_cents(int(payment["amount"]))
        customer_name_field.value = sale["customer_name"] or ""
        customer_note_field.value = sale["customer_note"] or ""
        edit_banner.visible = True
        edit_banner.content = ft.Row(
            [
                ft.Text(
                    strings_es.SALES_EDIT_MODE.format(logical_id=editing_logical_id),
                    color=ft.Colors.BROWN_900,
                ),
                cancel_edit_button,
            ],
            spacing=12,
        )
        _set_status("")
        redraw_cart()
        _payment_hint()
        _update()

    def _cancel_edit(e) -> None:
        nonlocal editing_logical_id
        editing_logical_id = None
        edit_banner.visible = False
        cart.clear()
        _clear_form()
        _set_status("")
        _update()

    def _void_sale(index: int) -> None:
        row = recent_rows[index]
        logical_id = int(row["logical_id"])

        def _do_void(e) -> None:
            nonlocal editing_logical_id
            try:
                sales_repo.void_sale(conn, logical_id, session.user_id)
            except ValidationError as exc:
                _set_status(sales_controller.translate_write_error(exc))
                _update()
                return
            if editing_logical_id == logical_id:
                editing_logical_id = None
                cart.clear()
                edit_banner.visible = False
                _clear_form()
            _set_status(strings_es.SALES_SUCCESS_VOIDED, success=True)
            reload_recent()
            on_change()
            if page is not None:
                page.pop_dialog()
            _update()

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(strings_es.SALES_VOID_TITLE),
            content=ft.Text(strings_es.SALES_VOID_QUESTION),
            actions=[
                ft.TextButton(strings_es.COMMON_CANCEL, on_click=lambda e: page.pop_dialog() if page else None),
                ft.TextButton(strings_es.SALES_VOID_CONFIRM, on_click=_do_void),
            ],
        )
        _show_dialog(confirm_dialog)

    def _build_recent_row(row) -> ft.Control:
        items = sales_repo.get_sale_items(conn, int(row["id"]))
        payments = sales_repo.get_sale_payments(conn, int(row["id"]))
        total = sum(int(i["quantity"]) * int(i["unit_price_applied"]) for i in items)
        summary = format_items_summary(
            [dict(i) for i in items]
        )
        methods = sales_controller.format_methods_label(
            [dict(p) for p in payments],
            bool(row["is_credit"]),
            row["customer_name"],
        )
        body = f"{format_timestamp(int(row['timestamp']))}  •  {summary}  •  $ {format_cents(total)}"
        if methods:
            body += f"  •  {methods}"
        locked = bool(row["is_credit"]) and bool(row["has_collections"])
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(body, expand=True),
                    ft.IconButton(
                        icon=ft.Icons.EDIT,
                        disabled=locked,
                        tooltip=(
                            strings_es.SALES_EDIT_LOCKED_TOOLTIP
                            if locked
                            else strings_es.SALES_EDIT_BUTTON
                        ),
                        on_click=None if locked else lambda e, r=row: _open_edit(_row_index(r)),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.UNDO,
                        disabled=locked,
                        tooltip=(
                            strings_es.SALES_VOID_LOCKED_TOOLTIP
                            if locked
                            else strings_es.SALES_VOID_BUTTON
                        ),
                        on_click=None if locked else lambda e, r=row: _void_sale(_row_index(r)),
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
            border_radius=8,
            margin=ft.Margin.symmetric(vertical=4),
        )

    recent_rows: list = []

    def _row_index(row) -> int:
        return recent_rows.index(row)

    def reload_recent() -> None:
        nonlocal recent_rows
        recent_rows = sales_repo.list_current_sales(
            conn, since_ts=start_of_today_ts(), limit=50
        )
        if not recent_rows:
            recent_col.controls = [
                ft.Text(strings_es.SALES_EMPTY_RECENT, color=ft.Colors.GREY_600)
            ]
        else:
            recent_col.controls = [_build_recent_row(r) for r in recent_rows]
        _update()

    recent_col = ft.Column(spacing=2, expand=True, scroll=ft.ScrollMode.AUTO)

    add_button.on_click = _add_line
    submit_button.on_click = _on_submit
    credit_switch.on_change = _toggle_credit
    cancel_edit_button.on_click = _cancel_edit
    cash_field.on_change = lambda e: _payment_hint()
    qr_field.on_change = lambda e: _payment_hint()

    entry_form = ft.Container(
        content=ft.Column(
            [
                ft.Text(strings_es.SALES_TITLE, size=20, weight=ft.FontWeight.BOLD),
                edit_banner,
                ft.Row([product_dropdown, quantity_field, add_button], spacing=12),
                ft.Text(strings_es.SALES_CART_TITLE, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=cart_list,
                    border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
                    border_radius=8,
                    padding=8,
                    height=180,
                ),
                total_text,
                credit_switch,
                payment_row,
                customer_fields,
                submit_button,
                status_text,
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=16,
        width=600,
        expand=True,
    )

    recent_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text(strings_es.SALES_RECENT_TITLE, size=20, weight=ft.FontWeight.BOLD),
                recent_col,
            ],
            spacing=10,
            expand=True,
        ),
        padding=16,
        width=520,
        expand=True,
    )

    customer_fields.visible = False
    payment_hint.value = ""
    redraw_cart()
    reload_recent()

    return ft.Row([entry_form, ft.VerticalDivider(width=1), recent_panel], expand=True)
