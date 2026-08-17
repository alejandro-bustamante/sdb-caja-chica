"""Pure controller logic for the Auditoría screen — no Flet imports.

Summary builders (plan-05 Task 2) turn an :class:`audit.AuditEvent` into a
single Spanish sentence at the level of business facts a shop owner cares
about — who, what, how much. Implementation details of the append-only design
(``logical_id``, ``version``, ``superseded_at``, ``deleted_at``) are never
mentioned in any UI text (plan-05 Task 2.2). Every template lives in
``strings_es.py``.

``detail_lines`` (plan-05 Task 4) builds the expandable before/after
comparison for edited/voided sales and expenses, reusing the existing history
read helpers (``sales_repo.get_sale_history`` / ``get_sale_items`` /
``get_sale_payments``) plus the previous-version fields the audit query
already attaches to expense events — no new repository read functions.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from app.db.repositories import sales as sales_repo
from app.db.repositories import users as users_repo
from app.domain import audit
from app.domain.balance import format_cents
from app.ui import strings_es
from app.ui.views.common_controller import (
    format_items_summary,
    format_payment_breakdown,
)

CATEGORY_LABELS = {
    audit.CATEGORY_SALES: strings_es.NAV_VENTAS,
    audit.CATEGORY_CATALOG: strings_es.NAV_CATALOGO,
    audit.CATEGORY_RESTOCK: strings_es.NAV_RESTOCK,
    audit.CATEGORY_EXPENSES: strings_es.NAV_GASTOS,
    audit.CATEGORY_DEBTS: strings_es.NAV_FIADO,
    audit.CATEGORY_CASH_COUNTS: strings_es.NAV_ARQUEO,
}

CHANGE_TYPE_LABELS = {
    audit.CHANGE_REGISTRO: strings_es.AUDIT_TYPE_REGISTRO,
    audit.CHANGE_EDICION: strings_es.AUDIT_TYPE_EDICION,
    audit.CHANGE_ELIMINACION: strings_es.AUDIT_TYPE_ELIMINACION,
}

TIME_PRESET_LABELS = {
    "1h": strings_es.AUDIT_TIME_1H,
    "24h": strings_es.AUDIT_TIME_24H,
    "7d": strings_es.AUDIT_TIME_7D,
    "30d": strings_es.AUDIT_TIME_30D,
    audit.TIME_PRESET_ALL: strings_es.AUDIT_TIME_ALL,
}


def category_label(key: str) -> str:
    return CATEGORY_LABELS[key]


def change_type_label(key: str) -> str:
    return CHANGE_TYPE_LABELS[key]


def time_preset_label(key: str) -> str:
    return TIME_PRESET_LABELS[key]


def default_time_preset() -> str:
    """The screen's first-load time filter (plan-05 Task 3.2): 24 hours, so
    opening the screen never fetches a long ledger's entire history."""
    return "24h"


def _money(cents: int | None) -> str:
    """``$30.00``-style display value (the currency symbol, like elsewhere
    in the views, is not a translatable string)."""
    return f"${format_cents(cents or 0)}"


def _methods_label(event: audit.AuditEvent) -> str:
    """Payment methods as a Spanish phrase: ``efectivo + QR`` / ``efectivo`` /
    ``fiado`` (credit sales have no payments)."""
    if event.is_credit:
        return strings_es.AUDIT_METHOD_CREDIT
    labels: list[str] = []
    for method in (event.payment_methods or "").split(","):
        if method == "cash":
            labels.append(strings_es.AUDIT_METHOD_CASH)
        elif method == "qr":
            labels.append(strings_es.AUDIT_METHOD_QR)
    if not labels:
        return strings_es.AUDIT_METHOD_CREDIT
    return strings_es.AUDIT_METHODS_JOIN.join(labels)


def summary_for(event: audit.AuditEvent) -> str:
    """One Spanish sentence for an audit row, by category and change type."""
    builders = {
        audit.CATEGORY_SALES: _ventas_summary,
        audit.CATEGORY_CATALOG: _catalogo_summary,
        audit.CATEGORY_RESTOCK: _restock_summary,
        audit.CATEGORY_EXPENSES: _gastos_summary,
        audit.CATEGORY_DEBTS: _fiado_summary,
        audit.CATEGORY_CASH_COUNTS: _arqueo_summary,
    }
    return builders[event.category](event)


def _ventas_summary(event: audit.AuditEvent) -> str:
    amount = format_cents(event.amount or 0)
    if event.change_type == audit.CHANGE_ELIMINACION:
        return strings_es.AUDIT_VENTAS_ELIMINACION.format(user=event.user_name, amount=amount)
    if event.change_type == audit.CHANGE_EDICION:
        return strings_es.AUDIT_VENTAS_EDICION.format(user=event.user_name, amount=amount)
    return strings_es.AUDIT_VENTAS_REGISTRO.format(
        user=event.user_name, amount=amount, methods=_methods_label(event)
    )


def _catalogo_summary(event: audit.AuditEvent) -> str:
    name = event.product_name or "?"
    if event.change_type == audit.CHANGE_EDICION:
        return strings_es.AUDIT_CATALOGO_EDICION.format(
            name=name,
            user=event.user_name,
            old=format_cents(event.previous_price or 0),
            new=format_cents(event.price or 0),
        )
    return strings_es.AUDIT_CATALOGO_REGISTRO.format(
        name=name, user=event.user_name, price=format_cents(event.price or 0)
    )


def _restock_summary(event: audit.AuditEvent) -> str:
    return strings_es.AUDIT_RESTOCK_REGISTRO.format(
        user=event.user_name, items=event.items_summary or "—"
    )


def _gastos_summary(event: audit.AuditEvent) -> str:
    description = event.description or "?"
    if event.change_type == audit.CHANGE_ELIMINACION:
        return strings_es.AUDIT_GASTOS_ELIMINACION.format(
            description=description, user=event.user_name
        )
    amount = format_cents(event.amount or 0)
    if event.change_type == audit.CHANGE_EDICION:
        return strings_es.AUDIT_GASTOS_EDICION.format(
            description=description, user=event.user_name, amount=amount
        )
    return strings_es.AUDIT_GASTOS_REGISTRO.format(
        description=description, user=event.user_name, amount=amount
    )


def _fiado_summary(event: audit.AuditEvent) -> str:
    return strings_es.AUDIT_FIADO_REGISTRO.format(
        amount=format_cents(event.amount or 0),
        customer=event.customer_name or "?",
        user=event.user_name,
    )


def _arqueo_summary(event: audit.AuditEvent) -> str:
    return strings_es.AUDIT_ARQUEO_REGISTRO.format(
        user=event.user_name,
        counted=format_cents(event.amount or 0),
        expected=format_cents(event.expected_cash or 0),
        diff=format_cents(event.difference or 0),
    )


def detail_available(event: audit.AuditEvent) -> bool:
    """Whether the row offers the expandable before/after detail (Task 4).

    Only edited/voided sales and expenses have anything to compare — the
    other categories never change after creation, and a catalog price change
    is already fully described by its summary sentence.
    """
    if event.change_type == audit.CHANGE_REGISTRO:
        return False
    return event.category in (audit.CATEGORY_SALES, audit.CATEGORY_EXPENSES)


def detail_lines(conn: sqlite3.Connection, event: audit.AuditEvent) -> list[str]:
    """Spanish before/after lines for an edited/voided sale or expense."""
    if event.category == audit.CATEGORY_SALES:
        return _sale_detail_lines(conn, event)
    if event.category == audit.CATEGORY_EXPENSES:
        return _expense_detail_lines(event)
    return []


def _sale_content_lines(
    conn: sqlite3.Connection, sale_row
) -> list[str]:
    """The content of one sale version, as plain business lines."""
    items = sales_repo.get_sale_items(conn, int(sale_row["id"]))
    total = sum(
        int(item["quantity"]) * int(item["unit_price_applied"]) for item in items
    )
    payments = [dict(p) for p in sales_repo.get_sale_payments(conn, int(sale_row["id"]))]
    lines = [strings_es.AUDIT_DETAIL_TOTAL.format(amount=format_cents(total))]
    if items:
        lines.append(
            strings_es.AUDIT_DETAIL_ITEMS.format(items=format_items_summary(items))
        )
    if payments:
        lines.append(
            strings_es.AUDIT_DETAIL_PAYMENT_LABEL
            + ": "
            + format_payment_breakdown(payments)
        )
    return lines


def _sale_detail_lines(conn: sqlite3.Connection, event: audit.AuditEvent) -> list[str]:
    if event.entity_logical_id is None:
        return []
    history = sales_repo.get_sale_history(conn, event.entity_logical_id)
    if not history:
        return []
    if event.change_type == audit.CHANGE_ELIMINACION:
        # The voided version itself carries no items — show what was voided
        # from the last active version.
        source = history[-2] if len(history) >= 2 else history[-1]
        return [strings_es.AUDIT_DETAIL_VOIDED_PREFIX] + _sale_content_lines(
            conn, source
        )
    current = next((r for r in history if r["version"] == event.version), None)
    previous = next(
        (r for r in history if r["version"] == (event.version or 0) - 1), None
    )
    if current is None or previous is None:
        return []
    lines: list[str] = []

    prev_items = {
        row["product_name"]: row
        for row in sales_repo.get_sale_items(conn, int(previous["id"]))
    }
    cur_items = {
        row["product_name"]: row
        for row in sales_repo.get_sale_items(conn, int(current["id"]))
    }
    for name in sorted(set(prev_items) | set(cur_items)):
        qty_before = int(prev_items[name]["quantity"]) if name in prev_items else 0
        qty_after = int(cur_items[name]["quantity"]) if name in cur_items else 0
        if qty_before != qty_after:
            lines.append(
                strings_es.AUDIT_DETAIL_FIELD.format(
                    field=f"{strings_es.SALES_QUANTITY_LABEL} '{name}'",
                    before=qty_before,
                    after=qty_after,
                )
            )

    def _total(items) -> int:
        return sum(
            int(item["quantity"]) * int(item["unit_price_applied"])
            for item in items.values()
        )

    total_before, total_after = _total(prev_items), _total(cur_items)
    if total_before != total_after:
        lines.append(
            strings_es.AUDIT_DETAIL_FIELD.format(
                field=strings_es.EXPORT_COL_TOTAL,
                before=_money(total_before),
                after=_money(total_after),
            )
        )

    payments_before = format_payment_breakdown(
        [dict(p) for p in sales_repo.get_sale_payments(conn, int(previous["id"]))]
    )
    payments_after = format_payment_breakdown(
        [dict(p) for p in sales_repo.get_sale_payments(conn, int(current["id"]))]
    )
    if payments_before != payments_after:
        lines.append(
            strings_es.AUDIT_DETAIL_FIELD.format(
                field=strings_es.AUDIT_DETAIL_PAYMENT_LABEL,
                before=payments_before,
                after=payments_after,
            )
        )

    user_before = users_repo.get_user(conn, int(previous["current_user"]))
    user_after = users_repo.get_user(conn, int(current["current_user"]))
    if (
        user_before is not None
        and user_after is not None
        and user_before.id != user_after.id
    ):
        lines.append(
            strings_es.AUDIT_DETAIL_FIELD.format(
                field=strings_es.CURRENT_USER_LABEL,
                before=user_before.name,
                after=user_after.name,
            )
        )
    return lines


def _expense_detail_lines(event: audit.AuditEvent) -> list[str]:
    description = event.description or "?"
    if event.change_type == audit.CHANGE_ELIMINACION:
        return [
            strings_es.AUDIT_DETAIL_VOIDED_PREFIX,
            strings_es.AUDIT_DETAIL_DESCRIPTION.format(description=description),
            strings_es.AUDIT_DETAIL_TOTAL.format(
                amount=format_cents(event.amount or 0)
            ),
        ]
    lines: list[str] = []
    if event.prev_description != description:
        lines.append(
            strings_es.AUDIT_DETAIL_FIELD.format(
                field=strings_es.EXPENSES_DESCRIPTION_LABEL,
                before=event.prev_description or "",
                after=description,
            )
        )
    if event.prev_amount != event.amount:
        lines.append(
            strings_es.AUDIT_DETAIL_FIELD.format(
                field=strings_es.EXPORT_COL_TOTAL,
                before=_money(event.prev_amount),
                after=_money(event.amount),
            )
        )
    return lines


def default_file_name() -> str:
    """Suggested workbook filename for the dedicated audit export."""
    return strings_es.AUDIT_EXPORT_FILE_NAME.format(date=date.today().isoformat())
