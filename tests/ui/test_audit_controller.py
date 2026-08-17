"""Tests for the Auditoría screen's pure controller (plan-05 Task 2 & 4).

One summary assertion per (category, change_type) combination that is
actually reachable per plan-05 Task 1.1's table — e.g. there is deliberately
no "Catálogo, eliminación" test, since that combination never occurs.
"""

from __future__ import annotations

from app.db.repositories import batches as batches_repo
from app.db.repositories import cash_counts as cash_counts_repo
from app.db.repositories import debts as debts_repo
from app.db.repositories import expenses as expenses_repo
from app.db.repositories import products as products_repo
from app.db.repositories import sales as sales_repo
from app.domain import audit
from app.domain.types import ExpensePaymentInput, SaleItemInput, SalePaymentInput
from app.ui import strings_es
from app.ui.views import audit_controller


def _seed(conn, user_id):
    pid = products_repo.create_product(conn, "Coca-Cola 600ml", 1500, user_id)
    products_repo.update_product_price(conn, pid, 1800, user_id)
    batches_repo.create_batch(
        conn, [(pid, 10)], [ExpensePaymentInput("cash", 5000)], "flete", user_id
    )
    cash_sale_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1500)],
        [SalePaymentInput("cash", 3000)],
        False,
        None,
        None,
        user_id,
    )
    sales_repo.edit_sale(
        conn,
        cash_sale_id,
        [SaleItemInput(product_id=pid, quantity=3, unit_price_applied=1500)],
        [SalePaymentInput("cash", 4500)],
        False,
        None,
        None,
        user_id,
    )
    credit_sale_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=1500)],
        [],
        True,
        "María Pérez",
        None,
        user_id,
    )
    debts_repo.record_partial_payment(conn, _logical_id(conn, credit_sale_id), 500, user_id)
    expense_id = expenses_repo.create_expense(
        conn, "Alquiler local", [ExpensePaymentInput("cash", 3000)], user_id
    )
    expenses_repo.edit_expense(
        conn,
        _expense_logical_id(conn, expense_id),
        "Alquiler local (nuevo)",
        [ExpensePaymentInput("cash", 3500)],
        user_id,
    )
    other_expense_id = expenses_repo.create_expense(
        conn, "Flete", [ExpensePaymentInput("cash", 2000)], user_id
    )
    expenses_repo.void_expense(conn, _expense_logical_id(conn, other_expense_id), user_id)
    cash_counts_repo.record_cash_count(conn, counted_cash=1000, user_id=user_id)
    return pid, cash_sale_id, credit_sale_id, expense_id


def _events(conn, **filters):
    return audit.list_audit_events(conn, limit=200, **filters)


def _logical_id(conn, sale_id: int) -> int:
    """The logical id of a sale row id (create_sale returns the physical row
    id, while the debts/sales repos take logical ids)."""
    row = conn.execute(
        "SELECT logical_id FROM sales WHERE id = ?", (sale_id,)
    ).fetchone()
    assert row is not None
    return int(row["logical_id"])


def _expense_logical_id(conn, expense_row_id: int) -> int:
    """The logical id of an expense row id (same divergence as sales)."""
    row = conn.execute(
        "SELECT logical_id FROM expenses WHERE id = ?", (expense_row_id,)
    ).fetchone()
    assert row is not None
    return int(row["logical_id"])


# --- Ventas ----------------------------------------------------------------

def test_ventas_registro_summary(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_SALES,))
        if e.change_type == audit.CHANGE_REGISTRO and e.is_credit is False
    )
    summary = audit_controller.summary_for(event)
    assert "Venta registrada por Alice" in summary
    assert "$30.00" in summary
    assert "(efectivo)" in summary


def test_ventas_edicion_summary(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_SALES,))
        if e.change_type == audit.CHANGE_EDICION
    )
    assert "Venta editada por Alice" in audit_controller.summary_for(event)
    assert "$45.00" in audit_controller.summary_for(event)


def test_ventas_eliminacion_summary_uses_previous_total(conn, user_id):
    pid = products_repo.create_product(conn, "Azúcar", 1000, user_id)
    sale_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1000)],
        [SalePaymentInput("cash", 2000)],
        False,
        None,
        None,
        user_id,
    )
    sales_repo.void_sale(conn, sale_id, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_SALES,))
        if e.change_type == audit.CHANGE_ELIMINACION
    )
    summary = audit_controller.summary_for(event)
    assert "Venta anulada por Alice" in summary
    assert "$20.00" in summary  # the voided version's own total would be $0.00


def test_ventas_split_payment_methods_label(conn, user_id):
    pid = products_repo.create_product(conn, "Pan", 500, user_id)
    sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=500)],
        [SalePaymentInput("cash", 300), SalePaymentInput("qr", 200)],
        False,
        None,
        None,
        user_id,
    )
    event = _events(conn, categories=(audit.CATEGORY_SALES,))[0]
    assert "(efectivo + QR)" in audit_controller.summary_for(event)


def test_ventas_credit_summary_methods_label(conn, user_id):
    pid = products_repo.create_product(conn, "Pan", 500, user_id)
    sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=500)],
        [],
        True,
        "Pepe",
        None,
        user_id,
    )
    event = _events(conn, categories=(audit.CATEGORY_SALES,))[0]
    assert "(fiado)" in audit_controller.summary_for(event)


# --- Catálogo --------------------------------------------------------------

def test_catalogo_registro_summary(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_CATALOG,))
        if e.change_type == audit.CHANGE_REGISTRO
    )
    summary = audit_controller.summary_for(event)
    assert "Producto 'Coca-Cola 600ml' creado por Alice" in summary
    assert "$15.00" in summary


def test_catalogo_edicion_summary(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_CATALOG,))
        if e.change_type == audit.CHANGE_EDICION
    )
    summary = audit_controller.summary_for(event)
    assert "Precio de 'Coca-Cola 600ml' editado por Alice" in summary
    assert "$15.00 → $18.00" in summary


# --- Reponer stock ----------------------------------------------------------

def test_restock_summary(conn, user_id):
    _seed(conn, user_id)
    event = _events(conn, categories=(audit.CATEGORY_RESTOCK,))[0]
    summary = audit_controller.summary_for(event)
    assert "Reposición por Alice" in summary
    assert "Coca-Cola 600ml x10" in summary


# --- Gastos ----------------------------------------------------------------

def test_gastos_registro_summary(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_EXPENSES,))
        if e.change_type == audit.CHANGE_REGISTRO
        and e.description == "Alquiler local"
    )
    summary = audit_controller.summary_for(event)
    assert "Gasto 'Alquiler local' registrado por Alice" in summary
    assert "$30.00" in summary


def test_gastos_edicion_summary(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_EXPENSES,))
        if e.change_type == audit.CHANGE_EDICION
    )
    summary = audit_controller.summary_for(event)
    assert "Gasto 'Alquiler local (nuevo)' editado por Alice" in summary
    assert "$35.00" in summary


def test_gastos_eliminacion_summary(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_EXPENSES,))
        if e.change_type == audit.CHANGE_ELIMINACION
    )
    assert "Gasto 'Flete' anulado por Alice" == audit_controller.summary_for(event)


# --- Fiado -----------------------------------------------------------------

def test_fiado_summary(conn, user_id):
    _seed(conn, user_id)
    event = _events(conn, categories=(audit.CATEGORY_DEBTS,))[0]
    summary = audit_controller.summary_for(event)
    assert "Abono de $5.00 recibido de 'María Pérez' por Alice" == summary


# --- Arqueo ----------------------------------------------------------------

def test_arqueo_summary(conn, user_id):
    _seed(conn, user_id)
    event = _events(conn, categories=(audit.CATEGORY_CASH_COUNTS,))[0]
    summary = audit_controller.summary_for(event)
    assert "Arqueo por Alice" in summary
    assert "contado $10.00" in summary
    assert "esperado" in summary
    assert "diferencia" in summary


# --- Labels / presets -------------------------------------------------------

def test_labels_and_presets():
    assert audit_controller.category_label(audit.CATEGORY_SALES) == strings_es.NAV_VENTAS
    assert audit_controller.change_type_label(audit.CHANGE_ELIMINACION) == strings_es.AUDIT_TYPE_ELIMINACION
    assert audit_controller.time_preset_label("24h") == strings_es.AUDIT_TIME_24H
    assert audit_controller.default_time_preset() == "24h"
    assert "auditoria_" in audit_controller.default_file_name()


# --- Task 4: expandable before/after detail ----------------------------------

def test_detail_available_only_for_edited_or_voided_sales_and_expenses(conn, user_id):
    _seed(conn, user_id)
    for event in _events(conn):
        expected = event.change_type != audit.CHANGE_REGISTRO and event.category in (
            audit.CATEGORY_SALES,
            audit.CATEGORY_EXPENSES,
        )
        assert audit_controller.detail_available(event) == expected, (
            event.category,
            event.change_type,
        )


def test_sale_edit_detail_shows_changed_fields(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_SALES,))
        if e.change_type == audit.CHANGE_EDICION
    )
    lines = audit_controller.detail_lines(conn, event)
    assert "Cantidad 'Coca-Cola 600ml': 2 → 3" in lines
    assert "Total: $30.00 → $45.00" in lines
    assert any("Pago" in line and "Efectivo $ 30.00" in line and "Efectivo $ 45.00" in line for line in lines)


def test_sale_reassign_detail_shows_user_change(conn, user_id, other_user_id):
    pid = products_repo.create_product(conn, "Pan", 500, user_id)
    sale_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=1, unit_price_applied=500)],
        [SalePaymentInput("cash", 500)],
        False,
        None,
        None,
        user_id,
    )
    sales_repo.reassign_sale_user(conn, sale_id, other_user_id, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_SALES,))
        if e.change_type == audit.CHANGE_EDICION
    )
    lines = audit_controller.detail_lines(conn, event)
    assert lines == ["Usuario actual: Alice → Blanca"]


def test_voided_sale_detail_shows_what_was_voided(conn, user_id):
    pid = products_repo.create_product(conn, "Azúcar", 1000, user_id)
    sale_id = sales_repo.create_sale(
        conn,
        [SaleItemInput(product_id=pid, quantity=2, unit_price_applied=1000)],
        [SalePaymentInput("cash", 2000)],
        False,
        None,
        None,
        user_id,
    )
    sales_repo.void_sale(conn, sale_id, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_SALES,))
        if e.change_type == audit.CHANGE_ELIMINACION
    )
    lines = audit_controller.detail_lines(conn, event)
    assert lines[0] == strings_es.AUDIT_DETAIL_VOIDED_PREFIX
    assert "Total: $ 20.00" in lines
    assert any("Azúcar x2" in line for line in lines)


def test_expense_edit_detail_shows_changed_fields(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_EXPENSES,))
        if e.change_type == audit.CHANGE_EDICION
    )
    lines = audit_controller.detail_lines(conn, event)
    assert "Descripción: Alquiler local → Alquiler local (nuevo)" in lines
    assert "Total: $30.00 → $35.00" in lines


def test_voided_expense_detail(conn, user_id):
    _seed(conn, user_id)
    event = next(
        e
        for e in _events(conn, categories=(audit.CATEGORY_EXPENSES,))
        if e.change_type == audit.CHANGE_ELIMINACION
    )
    lines = audit_controller.detail_lines(conn, event)
    assert lines[0] == strings_es.AUDIT_DETAIL_VOIDED_PREFIX
    assert "Descripción: 'Flete'" in lines
    assert "Total: $ 20.00" in lines


def test_detail_lines_empty_for_non_detail_categories(conn, user_id):
    _seed(conn, user_id)
    restock = _events(conn, categories=(audit.CATEGORY_RESTOCK,))[0]
    assert audit_controller.detail_lines(conn, restock) == []
    catalogo = _events(conn, categories=(audit.CATEGORY_CATALOG,))[0]
    assert audit_controller.detail_lines(conn, catalogo) == []
