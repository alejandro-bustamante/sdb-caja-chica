"""Application shell: persistent user bar + balance banner mounted once, and a
navigation rail switching a single content area between the six daily-use
screens (AGENTS.md §7 — the header elements are structural, not per-screen).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.ui import strings_es
from app.ui.components.balance_banner import BalanceBanner
from app.ui.components.user_bar import build_user_bar
from app.ui.session import Session
from app.ui.views import (
    cash_counts,
    catalog,
    debts,
    expenses,
    restock,
)
from app.ui.views import (
    sales as sales_view,
)

_VIEW_BUILDERS = {
    "sales": sales_view.build,
    "catalog": catalog.build,
    "restock": restock.build,
    "expenses": expenses.build,
    "debts": debts.build,
    "cash_counts": cash_counts.build,
}

_ORDER = ["sales", "catalog", "restock", "expenses", "debts", "cash_counts"]


def build_shell(
    page: ft.Page, conn, session: Session
) -> ft.Control:
    banner = BalanceBanner()
    banner.refresh(conn)

    def refresh_balance() -> None:
        """Shared callback: recompute the banner after any write / nav change."""
        banner.refresh(conn)
        if page is not None:
            page.update()

    content_area = ft.Container(expand=True)

    def switch(key: str) -> None:
        builder: Callable = _VIEW_BUILDERS[key]
        content_area.content = builder(conn, session, refresh_balance, page=page)
        if page is not None:
            page.update()

    destinations = [
        ft.NavigationRailDestination(
            icon=ft.Icons.POINT_OF_SALE, label=strings_es.NAV_VENTAS
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.CATEGORY, label=strings_es.NAV_CATALOGO
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.INVENTORY_2, label=strings_es.NAV_RESTOCK
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.RECEIPT_LONG, label=strings_es.NAV_GASTOS
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.ACCOUNT_BALANCE_WALLET, label=strings_es.NAV_FIADO
        ),
        ft.NavigationRailDestination(
            icon=ft.Icons.CHECKLIST, label=strings_es.NAV_ARQUEO
        ),
    ]

    def on_nav_change(e) -> None:
        index = e.control.selected_index
        if 0 <= index < len(_ORDER):
            switch(_ORDER[index])

    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=110,
        width=110,
        destinations=destinations,
        on_change=on_nav_change,
    )

    switch("sales")

    return ft.Column(
        [
            build_user_bar(session.user_name),
            banner.control,
            ft.Row(
                [
                    rail,
                    ft.VerticalDivider(width=1),
                    content_area,
                ],
                expand=True,
                spacing=0,
            ),
        ],
        spacing=4,
        expand=True,
    )
