"""Catalog screen — create products, change prices (append-only history),
deactivate/reactivate. Inactive products are excluded from the sales picker.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.db.repositories import products as products_repo
from app.domain.balance import compute_current_stock, format_cents
from app.ui import strings_es
from app.ui.session import Session
from app.ui.views import catalog_controller


def build(
    conn,
    session: Session,
    on_change: Callable[[], None],
    page: ft.Page | None = None,
) -> ft.Control:
    def _update() -> None:
        if page is not None:
            page.update()

    name_field = ft.TextField(label=strings_es.CATALOG_NAME_LABEL, expand=True)
    price_field = ft.TextField(
        label=strings_es.CATALOG_PRICE_LABEL, keyboard_type=ft.KeyboardType.NUMBER, width=140
    )
    create_button = ft.Button(strings_es.CATALOG_CREATE_BUTTON)
    create_status = ft.Text("", color=ft.Colors.RED_700)
    show_inactive = ft.Switch(label=strings_es.CATALOG_SHOW_INACTIVE, value=False)
    product_list = ft.Column(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)

    def _list() -> None:
        products = products_repo.list_all_products(conn)
        visible = [p for p in products if show_inactive.value or p.active]
        if not visible:
            product_list.controls = [
                ft.Text(strings_es.CATALOG_NO_PRODUCTS, color=ft.Colors.GREY_600)
            ]
        else:
            product_list.controls = [_build_product_row(p) for p in visible]
        _update()

    def _build_product_row(product) -> ft.Control:
        price_text = (
            f"$ {format_cents(product.current_price)}"
            if product.current_price is not None
            else strings_es.CATALOG_PRICE_NEVER_SET
        )
        inactive_badge = ft.Container(
            content=ft.Text(
                strings_es.CATALOG_INACTIVE_BADGE,
                color=ft.Colors.WHITE,
                size=11,
            ),
            bgcolor=ft.Colors.GREY_500,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            border_radius=6,
            visible=not product.active,
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(product.name, weight=ft.FontWeight.BOLD, expand=True),
                    inactive_badge,
                    ft.Text(price_text, width=110),
                    ft.Text(
                        f"{strings_es.CATALOG_STOCK_LABEL}: {compute_current_stock(conn, product.id)}",
                        width=90,
                    ),
                    ft.OutlinedButton(
                        strings_es.CATALOG_CHANGE_PRICE_BUTTON,
                        on_click=lambda e, pid=product.id, cur=product.current_price: _open_price_dialog(
                            pid, cur
                        ),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.UNDO if not product.active else ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        tooltip=(
                            strings_es.CATALOG_REACTIVATE_TOOLTIP
                            if not product.active
                            else strings_es.CATALOG_DEACTIVATE_TOOLTIP
                        ),
                        on_click=lambda e, pid=product.id, act=product.active: _toggle_active(
                            pid, act
                        ),
                    ),
                ],
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border=ft.Border.all(width=1, color=ft.Colors.GREY_300),
            border_radius=8,
        )

    def _toggle_active(product_id: int, currently_active: bool) -> None:
        products_repo.set_product_active(conn, product_id, not currently_active, session.user_id)
        _list()

    def _open_price_dialog(product_id: int, current_price: int | None) -> None:
        previous_text = (
            format_cents(current_price)
            if current_price is not None
            else strings_es.CATALOG_PRICE_NEVER_SET
        )
        price_input = ft.TextField(
            label=strings_es.CATALOG_NEW_PRICE_LABEL,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        reason_input = ft.TextField(label=strings_es.CATALOG_REASON_LABEL)
        error_text = ft.Text("", color=ft.Colors.RED_700)
        dialog = ft.AlertDialog(
            title=ft.Text(strings_es.CATALOG_CHANGE_PRICE_BUTTON),
            content=ft.Column(
                [
                    ft.Text(
                        strings_es.CATALOG_PREVIOUS_PRICE.format(price=previous_text),
                        color=ft.Colors.GREY_700,
                    ),
                    price_input,
                    reason_input,
                    error_text,
                ]
            ),
            actions=[
                ft.TextButton(strings_es.COMMON_CANCEL, on_click=lambda e: _close(dialog)),
                ft.TextButton(strings_es.CATALOG_SAVE_PRICE_BUTTON, on_click=lambda e: _save()),
            ],
        )

        def _save() -> None:
            error = catalog_controller.update_price_error(price_input.value)
            if error is not None:
                error_text.value = error
                _update()
                return
            parsed = catalog_controller.parse_money_input(price_input.value)
            assert parsed is not None
            products_repo.update_product_price(
                conn,
                product_id,
                parsed,
                session.user_id,
                reason=(reason_input.value or "").strip() or None,
            )
            _close(dialog)
            create_status.value = strings_es.CATALOG_SUCCESS_PRICE
            create_status.color = ft.Colors.GREEN_700
            _list()

        def _close(dlg) -> None:
            if page is not None:
                page.pop_dialog()
            _update()

        if page is not None:
            page.show_dialog(dialog)

    def _create_product(e) -> None:
        error = catalog_controller.create_form_error(name_field.value, price_field.value)
        if error is not None:
            create_status.value = error
            create_status.color = ft.Colors.RED_700
            _update()
            return
        parsed = catalog_controller.parse_money_input(price_field.value)
        assert parsed is not None
        products_repo.create_product(
            conn,
            (name_field.value or "").strip(),
            parsed,
            session.user_id,
        )
        create_status.value = strings_es.CATALOG_SUCCESS_CREATED
        create_status.color = ft.Colors.GREEN_700
        name_field.value = ""
        price_field.value = ""
        _list()

    create_button.on_click = _create_product
    show_inactive.on_change = lambda e: _list()

    _list()

    return ft.Container(
        padding=16,
        content=ft.Column(
            [
                ft.Text(strings_es.CATALOG_TITLE, size=20, weight=ft.FontWeight.BOLD),
                ft.Row([name_field, price_field, create_button], spacing=10),
                create_status,
                show_inactive,
                ft.Divider(height=8),
                ft.Container(
                    content=product_list,
                    padding=4,
                    expand=True,
                ),
            ],
            spacing=10,
            expand=True,
        ),
    )
