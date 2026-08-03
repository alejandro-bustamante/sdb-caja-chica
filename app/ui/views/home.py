"""Provider placeholder home screen: persistent user bar + total available.

This deliberately only demonstrates the two UI/UX invariants from
AGENTS.md §7 before any real screen exists.
"""

from __future__ import annotations

import flet as ft

from app.db.repositories import users as users_repo
from app.domain.balance import compute_available_cash, compute_available_qr, compute_total_available
from app.ui import strings_es
from app.ui.components.balance_banner import build_balance_banner
from app.ui.components.user_bar import build_user_bar


def build_home(page: ft.Page, conn, current_user_id: int) -> ft.Control:
    user = users_repo.get_user(conn, current_user_id)
    assert user is not None

    total = compute_total_available(conn)
    cash = compute_available_cash(conn)
    qr = compute_available_qr(conn)

    return ft.Column(
        [
            build_user_bar(user.name),
            build_balance_banner(total, cash, qr),
            ft.Text(
                f"{strings_es.MAIN_WELCOME}, {user.name}",
                size=18,
            ),
        ],
        spacing=4,
        expand=True,
    )
