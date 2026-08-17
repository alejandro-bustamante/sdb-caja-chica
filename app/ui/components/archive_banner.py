"""Read-only archive-mode header banner (plan-04 Task 3).

While the user browses an archived ledger nobody is "acting" in it, so the
persistent current-user bar (AGENTS.md §7) is swapped — only while
``read_only`` is true — for this equally hard-to-miss banner: the archived
filename plus a clear \"SOLO LECTURA\" label. The balance banner below stays:
the archived ledger's own historical balance is still useful to see.
"""

from __future__ import annotations

import flet as ft

from app.ui import strings_es


class ArchiveBanner:
    """Header banner shown while an archived ledger is open.

    ``set_filename(name)`` swaps the filename without rebuilding the widget
    tree, mirroring how ``BalanceBanner`` refreshes in place.
    """

    def __init__(self) -> None:
        self._filename_text = ft.Text(
            "",
            color=ft.Colors.WHITE,
            opacity=0.9,
            size=13,
        )
        self.control = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LOCK_OUTLINE, color=ft.Colors.WHITE),
                    ft.Text(
                        strings_es.ARCHIVE_READ_ONLY_LABEL,
                        color=ft.Colors.WHITE,
                        weight=ft.FontWeight.BOLD,
                        size=16,
                    ),
                    self._filename_text,
                ],
                spacing=8,
            ),
            bgcolor=ft.Colors.DEEP_ORANGE_800,
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            width=float("inf"),
        )

    def set_filename(self, filename: str) -> None:
        self._filename_text.value = (
            f"{filename} {strings_es.ARCHIVE_BANNER_SUFFIX}"
        )
