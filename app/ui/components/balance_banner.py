"""Balance banner — the single most prominent number (AGENTS.md §7)."""

from __future__ import annotations

import sqlite3

import flet as ft

from app.domain.balance import (
    compute_available_cash,
    compute_available_qr,
    compute_total_available,
    format_cents,
)
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


class BalanceBanner:
    """The prominent balance banner, self-refreshing from the ledger.

    Mounted once at the shell level (AGENTS.md §7). ``refresh(conn)``
    recomputes total/cash/QR and updates the existing widget values, so the
    shell can re-render the number after any write without rebuilding the
    widget tree.
    """

    def __init__(self) -> None:
        self._total_text = ft.Text(
            "$ 0.00",
            color=ft.Colors.WHITE,
            size=44,
            weight=ft.FontWeight.BOLD,
        )
        self._cash_text = ft.Text("", color=ft.Colors.WHITE)
        self._qr_text = ft.Text("", color=ft.Colors.WHITE)
        self.control = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        strings_es.BALANCE_LABEL.upper(),
                        color=ft.Colors.WHITE_70,
                        size=14,
                    ),
                    self._total_text,
                    ft.Row(
                        [self._cash_text, self._qr_text],
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

    def refresh(self, conn: sqlite3.Connection) -> None:
        total = compute_total_available(conn)
        cash = compute_available_cash(conn)
        qr = compute_available_qr(conn)
        self._total_text.value = f"$ {format_cents(total)}"
        self._cash_text.value = f"{strings_es.BALANCE_CASH_LABEL}: $ {format_cents(cash)}"
        self._qr_text.value = f"{strings_es.BALANCE_QR_LABEL}: $ {format_cents(qr)}"
