"""Custom calendar dialog for picking a date.

Flet's ``ft.DatePicker`` renders as a blank/transparent overlay in this
version's web client — the dialog never appears and the user is left staring
at a white screen they cannot dismiss. This component is a hand-rolled
month-grid picker built on the plain ``ft.AlertDialog`` primitive that is
already proven to work everywhere else in the app (see AGENTS.md: raw
primitives over framework conveniences when the framework one is broken).

Spanish UI text (weekday letters, month names, button labels) lives in
``strings_es`` per the language convention.
"""

from __future__ import annotations

import calendar
import datetime
from collections.abc import Callable

import flet as ft

from app.ui import strings_es

# Year bounds mirror the DatePicker bounds the export screen used before.
_MIN_YEAR = 2000
_MAX_YEAR = 2100

_DAY_SIZE = 40
_DAY_SPACING = 2


class CalendarDialog:
    """Modal month-grid date picker backed by an AlertDialog.

    The dialog owns its own state (viewed month/year) and closes itself after
    a date is picked or the user cancels; ``on_picked`` receives the chosen
    date when one is selected.
    """

    def __init__(
        self,
        page: ft.Page,
        initial: datetime.date | None,
        on_picked: Callable[[datetime.date], None],
    ) -> None:
        self.page = page
        self.on_picked = on_picked
        today = datetime.date.today()
        self.year = initial.year if initial else today.year
        self.month = initial.month if initial else today.month
        self.today = today

        self.month_label = ft.Text(
            self._month_title(), size=16, weight=ft.FontWeight.BOLD
        )
        self.grid = ft.Column(spacing=4)
        self._rebuild_grid()

        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(strings_es.CALENDAR_TITLE),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.IconButton(
                                    ft.Icons.CHEVRON_LEFT,
                                    tooltip=strings_es.CALENDAR_PREV,
                                    on_click=self._prev_month,
                                ),
                                self.month_label,
                                ft.IconButton(
                                    ft.Icons.CHEVRON_RIGHT,
                                    tooltip=strings_es.CALENDAR_NEXT,
                                    on_click=self._next_month,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=16,
                        ),
                        self.grid,
                    ],
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=4, vertical=4),
            ),
            actions=[
                ft.TextButton(
                    strings_es.CALENDAR_TODAY, on_click=lambda e: self._pick(self.today)
                ),
                ft.TextButton(strings_es.COMMON_CANCEL, on_click=lambda e: self._close()),
            ],
        )

    def show(self) -> None:
        self.page.show_dialog(self.dialog)

    # --- Internals ----------------------------------------------------------

    def _month_title(self) -> str:
        return f"{strings_es.CALENDAR_MONTHS[self.month - 1]} {self.year}"

    def _pick(self, date: datetime.date) -> None:
        self.on_picked(date)
        self._close()

    def _close(self) -> None:
        self.page.pop_dialog()
        self.page.update()

    def _prev_month(self, e=None) -> None:
        if self.year == _MIN_YEAR and self.month == 1:
            return
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        self._rebuild_grid()

    def _next_month(self, e=None) -> None:
        if self.year == _MAX_YEAR and self.month == 12:
            return
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        """Rebuild the weekday header + day grid for the viewed month."""
        self.month_label.value = self._month_title()

        first_weekday = datetime.date(self.year, self.month, 1).weekday()  # 0=Mon
        days_in_month = calendar.monthrange(self.year, self.month)[1]

        weeks: list[list[int | None]] = [[]]
        weeks[-1].extend([None] * first_weekday)
        for day in range(1, days_in_month + 1):
            if len(weeks[-1]) == 7:
                weeks.append([])
            weeks[-1].append(day)
        while len(weeks[-1]) < 7:
            weeks[-1].append(None)

        header = ft.Row(
            [
                ft.Text(
                    d,
                    width=_DAY_SIZE,
                    text_align=ft.TextAlign.CENTER,
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
                for d in strings_es.CALENDAR_WEEKDAYS
            ],
            spacing=_DAY_SPACING,
        )

        rows: list[ft.Control] = [header]
        for week in weeks:
            cells: list[ft.Control] = []
            for day in week:
                if day is None:
                    cells.append(ft.Container(width=_DAY_SIZE, height=_DAY_SIZE))
                    continue
                date = datetime.date(self.year, self.month, day)
                is_today = date == self.today
                cells.append(
                    ft.Container(
                        width=_DAY_SIZE,
                        height=_DAY_SIZE,
                        alignment=ft.Alignment.CENTER,
                        border_radius=8,
                        bgcolor=ft.Colors.PRIMARY if is_today else None,
                        ink=True,
                        on_click=lambda e, d=date: self._pick(d),
                        content=ft.Text(
                            str(day),
                            size=13,
                            color=(
                                ft.Colors.ON_PRIMARY
                                if is_today
                                else ft.Colors.ON_SURFACE
                            ),
                        ),
                    )
                )
            rows.append(ft.Row(cells, spacing=_DAY_SPACING))

        self.grid.controls = rows
