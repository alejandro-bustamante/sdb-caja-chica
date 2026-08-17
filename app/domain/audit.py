"""Normalized audit event query layer (plan-05 Task 1).

The Auditoría screen is a **read-only** query layer over the existing
append-only tables — no new tables, no denormalized "audit log" that could
drift out of sync with the real data (that would reintroduce exactly the
failure mode DESIGN.md §2 exists to prevent). Every event here is derived
from `sales`, `product_prices`, `batches`/`batch_items`, `expenses`,
`debt_payments` and `cash_counts` at query time.

Categories map 1:1 to the six daily nav screens so a user can always connect
an audit entry back to "the screen where I'd normally see this". Each event
is classified into exactly one of three change types:

  * registro — the first version of a versioned entity, or any row from a
    naturally single-event table (`debt_payments`, `cash_counts`, `batches`,
    first `product_prices` row of a product).
  * edicion — any later version of a versioned entity (a sale edit/reassign,
    an expense edit, a later `product_prices` row = price change).
  * eliminacion — any version with `deleted_at` set (voided sale/expense).

Known limitation (do NOT work around): `products.active` is a plain mutable
flag on the reference-style `products` row (AGENTS.md §1 explicitly allows
this one plain UPDATE), so activating/deactivating a product produces no row
anywhere that this module can query and does **not** appear in the audit
trail. Adding a parallel log table just for that one field would be exactly
the kind of denormalized, driftable audit log this module exists to avoid.

# TODO(reviewer): products.active has no history; would need Plan #1's
# decision revisited to version it.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

# --- Category / change-type keys --------------------------------------------
# Stable identifiers used in SQL and by the UI/controller. The Spanish labels
# users see live in `ui/strings_es.py` (reusing the NAV_* strings), never here.

CATEGORY_SALES = "ventas"
CATEGORY_CATALOG = "catalogo"
CATEGORY_RESTOCK = "restock"
CATEGORY_EXPENSES = "gastos"
CATEGORY_DEBTS = "fiado"
CATEGORY_CASH_COUNTS = "arqueo"

ALL_CATEGORIES = (
    CATEGORY_SALES,
    CATEGORY_CATALOG,
    CATEGORY_RESTOCK,
    CATEGORY_EXPENSES,
    CATEGORY_DEBTS,
    CATEGORY_CASH_COUNTS,
)

CHANGE_REGISTRO = "registro"
CHANGE_EDICION = "edicion"
CHANGE_ELIMINACION = "eliminacion"

ALL_CHANGE_TYPES = (CHANGE_REGISTRO, CHANGE_EDICION, CHANGE_ELIMINACION)

# Time presets: `key -> seconds`, used by `preset_since`. "Todo" (no lower
# bound) is represented by `TIME_PRESET_ALL` and is intentionally NOT silently
# capped — an audit tool that quietly hides old data defeats its purpose; it is
# simply paginated (see the Auditoría screen's "Cargar más").
TIME_PRESET_ALL = "todo"
TIME_PRESET_SECONDS = {
    "1h": 3600,
    "24h": 86400,
    "7d": 7 * 86400,
    "30d": 30 * 86400,
}


@dataclass(frozen=True)
class AuditEvent:
    """One normalized audit event, with enough underlying fields for the
    controller's summary builders (plan-05 Task 2) — nothing is discarded
    here just because the UI doesn't show every field by default.

    ``entity_logical_id`` is the versioned entity's logical id for the
    versioned tables (sales, expenses, product_prices via product id) and the
    credit sale's logical id for `debt_payments`; it is ``None`` for the
    naturally single-event tables (`batches`, `cash_counts`).
    """

    category: str
    change_type: str
    timestamp: int
    user_id: int
    user_name: str
    entity_logical_id: int | None = None

    # --- sales payload -----------------------------------------------------
    is_credit: bool | None = None
    customer_name: str | None = None
    amount: int | None = None  # sale total / expense amount / debt payment / counted cash
    payment_methods: str | None = None  # raw comma-separated keys: "cash,qr"

    # --- catalog payload ----------------------------------------------------
    product_name: str | None = None
    price: int | None = None
    previous_price: int | None = None

    # --- restock payload ----------------------------------------------------
    items_summary: str | None = None  # "Coca-Cola 600ml x10, Pan x5"
    expense_logical_id: int | None = None

    # --- cash count payload -------------------------------------------------
    expected_cash: int | None = None
    difference: int | None = None
    note: str | None = None

    # --- expenses payload ---------------------------------------------------
    description: str | None = None

    # --- versioning payload (used only by the Task 4 before/after detail;
    # never surfaced in UI text by name) -------------------------------------
    version: int | None = None  # event's own version, versioned tables only
    prev_description: str | None = None  # previous version's description
    prev_amount: int | None = None  # previous version's amount

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AuditEvent:
        return cls(
            category=str(row["category"]),
            change_type=str(row["change_type"]),
            timestamp=int(row["timestamp"]),
            user_id=int(row["user_id"]),
            user_name=str(row["user_name"]),
            entity_logical_id=_opt_int(row["entity_logical_id"]),
            is_credit=bool(row["is_credit"]) if row["is_credit"] is not None else None,
            customer_name=row["customer_name"],
            amount=_opt_int(row["amount"]),
            payment_methods=row["payment_methods"],
            product_name=row["product_name"],
            price=_opt_int(row["price"]),
            previous_price=_opt_int(row["previous_price"]),
            items_summary=row["items_summary"],
            expense_logical_id=_opt_int(row["expense_logical_id"]),
            expected_cash=_opt_int(row["expected_cash"]),
            difference=_opt_int(row["difference"]),
            note=row["note"],
            description=row["description"],
            version=_opt_int(row["version"]),
            prev_description=row["prev_description"],
            prev_amount=_opt_int(row["prev_amount"]),
        )


@dataclass(frozen=True)
class AuditFilters:
    """The filter state of the Auditoría screen, shared with the Excel export
    (plan-05 Task 5.2) so the exported workbook uses exactly the same
    predicates as the on-screen query.

    ``None`` means "no restriction" (all users / all categories / all change
    types / no time bound). ``categories``/``change_types`` are tuples of the
    stable keys above.
    """

    since: int | None = None
    until: int | None = None
    user_id: int | None = None
    categories: tuple[str, ...] | None = None
    change_types: tuple[str, ...] | None = None


def _opt_int(value) -> int | None:
    return None if value is None else int(value)


def preset_since(preset: str) -> int | None:
    """``since`` timestamp for a time preset key; ``None`` for "todo"."""
    if preset == TIME_PRESET_ALL:
        return None
    seconds = TIME_PRESET_SECONDS[preset]
    return int(time.time()) - seconds


# --- The union query ---------------------------------------------------------
# One branch per category. Column order is identical across branches (see the
# outer SELECT below). Change type is derived per branch with a CASE, so the
# change-type filter can run on the derived value in the outer WHERE. All
# timestamps are integer unix seconds; the catalog branch CASTs valid_from
# (a TEXT column that receives integer values) to be safe.
_AUDIT_EVENTS_UNION_SQL = """
    SELECT 'ventas' AS category,
           CASE WHEN s.deleted_at IS NOT NULL THEN 'eliminacion'
                WHEN s.version > 1 THEN 'edicion'
                ELSE 'registro' END AS change_type,
           s.timestamp AS timestamp,
           s.current_user AS user_id,
           u.name AS user_name,
           s.logical_id AS entity_logical_id,
           s.is_credit AS is_credit,
           s.customer_name AS customer_name,
           -- A voided sale version carries no items/payments of its own, so
           -- for eliminacion events the amount/methods come from the version
           -- being voided (its direct predecessor) — the summary must say
           -- "Venta anulada — $45.00", never "$0.00".
           CASE WHEN s.deleted_at IS NOT NULL AND s.version > 1 THEN (
                    SELECT COALESCE(SUM(si.quantity * si.unit_price_applied), 0)
                      FROM sale_items si
                      JOIN sales prev ON prev.id = si.sale_id
                     WHERE prev.logical_id = s.logical_id
                       AND prev.version = s.version - 1)
                ELSE (
                    SELECT COALESCE(SUM(si.quantity * si.unit_price_applied), 0)
                      FROM sale_items si WHERE si.sale_id = s.id)
           END AS amount,
           CASE WHEN s.deleted_at IS NOT NULL AND s.version > 1 THEN (
                    SELECT GROUP_CONCAT(sp.method, ',') FROM sale_payments sp
                      JOIN sales prev ON prev.id = sp.sale_id
                     WHERE prev.logical_id = s.logical_id
                       AND prev.version = s.version - 1)
                ELSE (
                    SELECT GROUP_CONCAT(sp.method, ',') FROM sale_payments sp
                     WHERE sp.sale_id = s.id)
           END AS payment_methods,
           NULL AS product_name, NULL AS price, NULL AS previous_price,
           NULL AS items_summary, NULL AS expense_logical_id,
           NULL AS expected_cash, NULL AS difference, NULL AS note,
           NULL AS description,
           s.version AS version,
           NULL AS prev_description, NULL AS prev_amount,
           s.id AS event_id
      FROM sales s
      JOIN users u ON u.id = s.current_user

    UNION ALL

    SELECT 'catalogo' AS category,
           CASE WHEN NOT EXISTS (
                      SELECT 1 FROM product_prices pp2
                       WHERE pp2.product_id = pp.product_id
                         AND pp2.id < pp.id)
                THEN 'registro' ELSE 'edicion' END AS change_type,
           CAST(pp.valid_from AS INTEGER) AS timestamp,
           pp.user_id AS user_id,
           u.name AS user_name,
           pp.product_id AS entity_logical_id,
           NULL AS is_credit, NULL AS customer_name,
           pp.price AS amount,
           NULL AS payment_methods,
           p.name AS product_name,
           pp.price AS price,
           (SELECT price FROM product_prices pp2
             WHERE pp2.product_id = pp.product_id AND pp2.id < pp.id
             ORDER BY pp2.id DESC LIMIT 1) AS previous_price,
           NULL AS items_summary, NULL AS expense_logical_id,
           NULL AS expected_cash, NULL AS difference, NULL AS note,
           NULL AS description,
           NULL AS version, NULL AS prev_description, NULL AS prev_amount,
           pp.id AS event_id
      FROM product_prices pp
      JOIN products p ON p.id = pp.product_id
      JOIN users u ON u.id = pp.user_id

    UNION ALL

    SELECT 'restock' AS category,
           'registro' AS change_type,
           b.timestamp AS timestamp,
           b.user_id AS user_id,
           u.name AS user_name,
           NULL AS entity_logical_id,
           NULL AS is_credit, NULL AS customer_name,
           NULL AS amount, NULL AS payment_methods,
           NULL AS product_name, NULL AS price, NULL AS previous_price,
           (SELECT GROUP_CONCAT(p.name || ' x' || bi.quantity, ', ')
              FROM batch_items bi JOIN products p ON p.id = bi.product_id
             WHERE bi.batch_id = b.id) AS items_summary,
           b.expense_logical_id AS expense_logical_id,
           NULL AS expected_cash, NULL AS difference, NULL AS note,
           NULL AS description,
           NULL AS version, NULL AS prev_description, NULL AS prev_amount,
           b.id AS event_id
      FROM batches b
      JOIN users u ON u.id = b.user_id

    UNION ALL

    SELECT 'gastos' AS category,
           CASE WHEN e.deleted_at IS NOT NULL THEN 'eliminacion'
                WHEN e.version > 1 THEN 'edicion'
                ELSE 'registro' END AS change_type,
           e.timestamp AS timestamp,
           e.user_id AS user_id,
           u.name AS user_name,
           e.logical_id AS entity_logical_id,
           NULL AS is_credit, NULL AS customer_name,
           e.amount AS amount, NULL AS payment_methods,
           NULL AS product_name, NULL AS price, NULL AS previous_price,
           NULL AS items_summary, NULL AS expense_logical_id,
           NULL AS expected_cash, NULL AS difference, NULL AS note,
           e.description AS description,
           e.version AS version,
           (SELECT description FROM expenses prev
             WHERE prev.logical_id = e.logical_id
               AND prev.version = e.version - 1) AS prev_description,
           (SELECT amount FROM expenses prev
             WHERE prev.logical_id = e.logical_id
               AND prev.version = e.version - 1) AS prev_amount,
           e.id AS event_id
      FROM expenses e
      JOIN users u ON u.id = e.user_id

    UNION ALL

    SELECT 'fiado' AS category,
           'registro' AS change_type,
           dp.timestamp AS timestamp,
           dp.user_id AS user_id,
           u.name AS user_name,
           s.logical_id AS entity_logical_id,
           NULL AS is_credit, s.customer_name AS customer_name,
           dp.amount AS amount, NULL AS payment_methods,
           NULL AS product_name, NULL AS price, NULL AS previous_price,
           NULL AS items_summary, NULL AS expense_logical_id,
           NULL AS expected_cash, NULL AS difference, NULL AS note,
           NULL AS description,
           NULL AS version, NULL AS prev_description, NULL AS prev_amount,
           dp.id AS event_id
      FROM debt_payments dp
      JOIN sales s ON s.id = dp.sale_id
      JOIN users u ON u.id = dp.user_id

    UNION ALL

    SELECT 'arqueo' AS category,
           'registro' AS change_type,
           cc.timestamp AS timestamp,
           cc.user_id AS user_id,
           u.name AS user_name,
           NULL AS entity_logical_id,
           NULL AS is_credit, NULL AS customer_name,
           cc.counted_cash AS amount, NULL AS payment_methods,
           NULL AS product_name, NULL AS price, NULL AS previous_price,
           NULL AS items_summary, NULL AS expense_logical_id,
           cc.expected_cash AS expected_cash,
           cc.difference AS difference,
           cc.note AS note,
           NULL AS description,
           NULL AS version, NULL AS prev_description, NULL AS prev_amount,
           cc.id AS event_id
      FROM cash_counts cc
      JOIN users u ON u.id = cc.user_id
"""

_AUDIT_COLUMNS = (
    "category, change_type, timestamp, user_id, user_name, entity_logical_id,"
    " is_credit, customer_name, amount, payment_methods, product_name, price,"
    " previous_price, items_summary, expense_logical_id, expected_cash,"
    " difference, note, description, version, prev_description, prev_amount"
)


def _validate_keys(keys: tuple[str, ...] | None, allowed: tuple[str, ...], label: str) -> None:
    if keys is None:
        return
    unknown = [k for k in keys if k not in allowed]
    if unknown:
        raise ValueError(f"Unknown audit {label} key(s): {unknown}")


def _where_clause(
    since: int | None,
    until: int | None,
    user_id: int | None,
    categories: tuple[str, ...] | None,
    change_types: tuple[str, ...] | None,
) -> tuple[str, list]:
    """Shared WHERE fragment + params for list and count queries, so the two
    can never disagree on what matches (plan-05 Task 1.2)."""
    clauses: list[str] = []
    params: list = []
    if since is not None:
        clauses.append("timestamp >= ?")
        params.append(since)
    if until is not None:
        clauses.append("timestamp <= ?")
        params.append(until)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if categories is not None:
        _validate_keys(tuple(categories), ALL_CATEGORIES, "category")
        clauses.append(f"category IN ({','.join('?' * len(categories))})")
        params.extend(categories)
    if change_types is not None:
        _validate_keys(tuple(change_types), ALL_CHANGE_TYPES, "change type")
        clauses.append(f"change_type IN ({','.join('?' * len(change_types))})")
        params.extend(change_types)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _run_query(
    conn: sqlite3.Connection,
    filters: AuditFilters,
    *,
    limit: int | None,
    offset: int,
) -> list[sqlite3.Row]:
    where, params = _where_clause(
        filters.since,
        filters.until,
        filters.user_id,
        filters.categories,
        filters.change_types,
    )
    sql = f"SELECT {_AUDIT_COLUMNS} FROM ({_AUDIT_EVENTS_UNION_SQL}) AS audit_events{where}"
    # (timestamp, category, event_id) is a total order, so pagination can
    # never skip or duplicate a row when many events share a timestamp.
    sql += " ORDER BY timestamp DESC, category, event_id DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    return conn.execute(sql, params).fetchall()


def list_audit_events(
    conn: sqlite3.Connection,
    *,
    since: int | None = None,
    until: int | None = None,
    user_id: int | None = None,
    categories: tuple[str, ...] | None = None,
    change_types: tuple[str, ...] | None = None,
    limit: int | None = 50,
    offset: int = 0,
) -> list[AuditEvent]:
    """Audit events matching the filters, newest first, paginated.

    ``limit=None`` returns every match (used by the Excel exports); a finite
    limit combines with ``offset`` for the screen's "Cargar más" pager.
    All filtering happens in SQL on the derived union — never by fetching
    everything and filtering in Python (plan-05 Task 1.2).
    """
    filters = AuditFilters(
        since=since,
        until=until,
        user_id=user_id,
        categories=categories,
        change_types=change_types,
    )
    rows = _run_query(conn, filters, limit=limit, offset=offset)
    return [AuditEvent.from_row(r) for r in rows]


def count_audit_events(
    conn: sqlite3.Connection,
    *,
    since: int | None = None,
    until: int | None = None,
    user_id: int | None = None,
    categories: tuple[str, ...] | None = None,
    change_types: tuple[str, ...] | None = None,
) -> int:
    """Total events matching the same filters as :func:`list_audit_events`."""
    filters = AuditFilters(
        since=since,
        until=until,
        user_id=user_id,
        categories=categories,
        change_types=change_types,
    )
    where, params = _where_clause(
        filters.since,
        filters.until,
        filters.user_id,
        filters.categories,
        filters.change_types,
    )
    row = conn.execute(
        f"SELECT COUNT(*) AS total FROM ({_AUDIT_EVENTS_UNION_SQL}) AS audit_events{where}",
        params,
    ).fetchone()
    return int(row["total"])
