"""Balance banner — the single most prominent number (AGENTS.md §7)."""

from __future__ import annotations

import flet as ft

from app.domain.balance import format_cents
from app.ui import strings_es


def build_balance_banner(
    total_cents: int, cash_cents: int, qr_cents: int
) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    strings_es.BALANCE_LABEL.upper(),
                    color=ft.Colors.WHITE_70,
                    size=14,
                ),
                ft.Text(
                    f"$ {format_cents(total_cents)}",
                    color=ft.Colors.WHITE,
                    size=44,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Row(
                    [
                        ft.Text(
                            f"{strings_es.BALANCE_CASH_LABEL}: $ {format_cents(cash_cents)}",
                            color=ft.Colors.WHITE,
                        ),
                        ft.Text(
                            f"{strings_es.BALANCE_QR_LABEL}: $ {format_cents(qr_cents)}",
                            color=ft.Colors.WHITE,
                        ),
                    ],
                    spacing=24,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        bgcolor=ft.Colors.GREEN_700,
        padding=ft.Padding.all(24),
        width=float("inf"),
        border_radius=12,
        margin=ft.Margin.symmetric(horizontal=16, vertical=8),
    )
