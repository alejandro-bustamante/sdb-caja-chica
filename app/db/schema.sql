-- =============================================================================
-- schema.sql — REFERENCE COPY of the current database shape.
--
-- NOTE: This file is NOT the source of truth for any existing SQLite file.
-- The source of truth is the numbered migration sequence in `db/migrations/`.
-- This file exists only as a human-readable "current shape" reference.
-- If you change the schema, add a new numbered migration AND update this
-- reference copy to match — never edit a past migration.
--
-- Conventions enforced throughout:
--   * Business data is append-only: versions are always INSERTed with the
--     same logical_id and incremented version; `superseded_at` / `deleted_at`
--     mark history. No UPDATE/DELETE on business tables (see AGENTS.md).
--   * Money is stored as INTEGER cents, never REAL/float.
--   * All FKs use ON DELETE RESTRICT (never CASCADE) to protect audit history.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- users — plain mutable reference table (the one permitted plain-UPDATE table)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

-- -----------------------------------------------------------------------------
-- products — mutable catalog ref; price history is append-only below
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT    NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

-- Append-only price history per product.
CREATE TABLE IF NOT EXISTS product_prices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    price         INTEGER NOT NULL CHECK (price >= 0),
    valid_from    TEXT    NOT NULL,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reason        TEXT,
    superseded_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_product_prices_product
    ON product_prices (product_id, superseded_at);

-- -----------------------------------------------------------------------------
-- expenses — versioned header (logical_id + version)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS expenses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    logical_id    INTEGER NOT NULL,
    version       INTEGER NOT NULL,
    superseded_at TEXT,
    deleted_at    TEXT,
    timestamp     INTEGER NOT NULL,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    description   TEXT    NOT NULL,
    amount        INTEGER NOT NULL CHECK (amount > 0),
    UNIQUE (logical_id, version)
);
CREATE INDEX IF NOT EXISTS idx_expenses_logical
    ON expenses (logical_id, version);

-- expense_payments — each expense version's payment split (cash and/or QR),
-- mirroring sale_payments. `expenses.amount` is the total of these payments.
CREATE TABLE IF NOT EXISTS expense_payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
    method     TEXT    NOT NULL CHECK (method IN ('cash', 'qr')),
    amount     INTEGER NOT NULL CHECK (amount > 0)
);
CREATE INDEX IF NOT EXISTS idx_expense_payments_expense
    ON expense_payments (expense_id);

-- ---------------------------------------------------------------------------
-- batches (restock) — purely logistical, links to the paying expense
-- `expense_logical_id` is a reference (not a FK): logical_id is not unique
-- across expense versions. Resolve it at read time to the current non-deleted
-- version of that logical_id (see repository helper).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS batches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           INTEGER NOT NULL,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    expense_logical_id  INTEGER
);

CREATE TABLE IF NOT EXISTS batch_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id   INTEGER NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity   INTEGER NOT NULL CHECK (quantity > 0)
);

-- -----------------------------------------------------------------------------
-- stock_movements — the stock ledger. quantity_delta is signed:
--   positive = restocked, negative = sold. Current stock = SUM(quantity_delta).
-- Exactly one source references the originating batch/sale item.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_movements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity_delta INTEGER NOT NULL CHECK (quantity_delta != 0),
    timestamp     INTEGER NOT NULL,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    batch_item_id INTEGER REFERENCES batch_items(id) ON DELETE RESTRICT,
    sale_item_id  INTEGER REFERENCES sale_items(id) ON DELETE RESTRICT,
    reason        TEXT,
    CHECK (
        (batch_item_id IS NOT NULL) <> (sale_item_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_stock_movements_product
    ON stock_movements (product_id);

-- -----------------------------------------------------------------------------
-- sales (versioned header) + sale_items + sale_payments
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sales (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    logical_id        INTEGER NOT NULL,
    version           INTEGER NOT NULL,
    superseded_at     TEXT,
    deleted_at        TEXT,
    timestamp         INTEGER NOT NULL,
    registered_by_user INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    current_user      INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    is_credit         INTEGER NOT NULL CHECK (is_credit IN (0, 1)),
    customer_name     TEXT,
    customer_note     TEXT,
    UNIQUE (logical_id, version)
);
CREATE INDEX IF NOT EXISTS idx_sales_logical ON sales (logical_id, version);

CREATE TABLE IF NOT EXISTS sale_items (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id                   INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
    product_id                INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity                  INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_applied        INTEGER NOT NULL CHECK (unit_price_applied >= 0),
    price_manually_overridden INTEGER NOT NULL DEFAULT 0 CHECK (price_manually_overridden IN (0, 1))
);

CREATE TABLE IF NOT EXISTS sale_payments (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id  INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
    method   TEXT    NOT NULL CHECK (method IN ('cash', 'qr')),
    amount   INTEGER NOT NULL CHECK (amount > 0)
);

-- -----------------------------------------------------------------------------
-- debt_payments — collections on credit sales (append-only ledger)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS debt_payments (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id   INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
    amount    INTEGER NOT NULL CHECK (amount > 0),
    timestamp INTEGER NOT NULL,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT
);

-- -----------------------------------------------------------------------------
-- cash_counts — immutable snapshots (never retroactively corrected)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cash_counts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     INTEGER NOT NULL,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    counted_cash  INTEGER NOT NULL CHECK (counted_cash >= 0),
    expected_cash INTEGER NOT NULL,
    difference    INTEGER NOT NULL,
    note          TEXT
);

-- -----------------------------------------------------------------------------
-- schema_version — append-only log of applied migrations
--   Current version = MAX(version). One row per applied migration.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    version    INTEGER NOT NULL,
    applied_at TEXT    NOT NULL
);