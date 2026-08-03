"""User picker view (mandatory at app start)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.db.repositories import users as users_repo
from app.ui import strings_es


def build_user_picker(
    page: ft.Page,
    conn,
    on_user_selected: Callable[[int], None],
) -> ft.Control:
    all_users = users_repo.list_all_users(conn)

    message = ft.Text(strings_es.USER_PICKER_PROMPT, size=16)
    name_field = ft.TextField(
        label=strings_es.USER_PICKER_CREATE_HINT,
        autofocus=True,
    )

    user_dropdown = ft.Dropdown(
        label=strings_es.USER_PICKER_TITLE,
        options=[ft.dropdown.Option(key=str(u.id), text=u.name) for u in all_users],
    )
    selected_id: list[int] = []

    def on_user_clicked(_):
        if user_dropdown.value:
            selected_id.append(int(user_dropdown.value))
            on_user_selected(int(user_dropdown.value))
        else:
            message.value = strings_es.USER_REQUIRED_ERROR
            page.update()

    def create_user(_):
        name = name_field.value.strip() if name_field.value else ""
        if not name:
            message.value = strings_es.USER_REQUIRED_ERROR
            page.update()
            return
        new_id = users_repo.create_user(conn, name)
        on_user_selected(new_id)

    return ft.Column(
        [
            ft.Text(strings_es.APP_TITLE, size=28, weight=ft.FontWeight.BOLD),
            message,
            user_dropdown,
            ft.Button(
                strings_es.USER_PICKER_SELECT_BUTTON, on_click=on_user_clicked
            ),
            ft.Divider(height=24),
            ft.Text(strings_es.USER_PICKER_CREATE_LABEL, opacity=0.7),
            name_field,
            ft.Button(strings_es.USER_PICKER_CREATE_BUTTON, on_click=create_user),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
        alignment=ft.MainAxisAlignment.CENTER,
    )
