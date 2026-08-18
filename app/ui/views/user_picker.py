"""User picker view (mandatory at app start).

Login is the primary action of this screen: selecting an existing user gets a
prominent filled button and most of the visual weight. Creating a user is a
secondary path (first run / new employee), visually smaller and below a
divider — still always reachable, never hidden (AGENTS.md §6: this is the only
identity mechanism, no real auth).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.db.repositories import users as users_repo
from app.ui import strings_es

# Card width keeps the two sections tidy on any monitor size.
_CARD_WIDTH = 440


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

    def _show_error() -> None:
        message.value = strings_es.USER_REQUIRED_ERROR
        message.color = ft.Colors.RED_700
        page.update()

    def on_user_clicked(_):
        if user_dropdown.value:
            selected_id.append(int(user_dropdown.value))
            on_user_selected(int(user_dropdown.value))
        else:
            _show_error()

    def create_user(_):
        name = name_field.value.strip() if name_field.value else ""
        if not name:
            _show_error()
            return
        new_id = users_repo.create_user(conn, name)
        on_user_selected(new_id)

    select_button = ft.Button(
        strings_es.USER_PICKER_SELECT_BUTTON, on_click=on_user_clicked, expand=True
    )
    create_button = ft.OutlinedButton(
        strings_es.USER_PICKER_CREATE_BUTTON, on_click=create_user, expand=True
    )

    login_children: list[ft.Control] = [message, user_dropdown, select_button]
    if not all_users:
        # First run: nothing to select yet — surface the hint and let the
        # (secondary) create path be the way in.
        select_button.disabled = True
        login_children.insert(
            1,
            ft.Text(
                strings_es.USER_PICKER_NO_USERS,
                color=ft.Colors.ON_SURFACE_VARIANT,
                size=12,
            ),
        )

    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            width=_CARD_WIDTH,
            padding=ft.Padding.all(28),
            border_radius=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border=ft.Border.all(
                width=1, color=ft.Colors.OUTLINE_VARIANT
            ),
            content=ft.Column(
                [
                    ft.Text(
                        strings_es.APP_TITLE, size=30, weight=ft.FontWeight.BOLD
                    ),
                    ft.Text(
                        strings_es.APP_SUBTITLE,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        size=14,
                    ),
                    ft.Container(height=8),
                    # --- Primary: log in as an existing user -----------------
                    *login_children,
                    ft.Container(height=12),
                    # --- Secondary: first-time user creation -----------------
                    ft.Divider(
                        height=1, color=ft.Colors.OUTLINE_VARIANT
                    ),
                    ft.Container(height=4),
                    ft.Text(
                        strings_es.USER_PICKER_CREATE_LABEL,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        size=13,
                    ),
                    name_field,
                    create_button,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=10,
            ),
        ),
    )
