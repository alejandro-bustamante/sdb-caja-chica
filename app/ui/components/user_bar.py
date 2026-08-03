"""Persistent current-user indicator bar (AGENTS.md §7: never remove/shrink)."""

from __future__ import annotations

import flet as ft

from app.ui import strings_es


def build_user_bar(current_user_name: str) -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.PERSON, color=ft.Colors.WHITE),
                ft.Text(
                    strings_es.CURRENT_USER_LABEL,
                    color=ft.Colors.WHITE,
                    opacity=0.85,
                    size=13,
                ),
                ft.Text(
                    current_user_name,
                    color=ft.Colors.WHITE,
                    weight=ft.FontWeight.BOLD,
                    size=16,
                ),
            ],
            spacing=8,
        ),
        bgcolor=ft.Colors.INDIGO_800,
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        width=float("inf"),
    )
