-- 0003: expenses become payable by cash and/or QR, mirroring sale_payments.
--
-- Expenses previously had a single `amount` subtracted entirely from the
-- cash drawer. To let the shop pay an expense (or a restock batch) by QR and
-- have it discounted from the QR money instead, each expense version now owns
-- a set of `expense_payments` rows (method + amount) exactly like
-- `sale_payments` do for sales. The version keeps its `amount` as the total
-- for display/history.

CREATE TABLE IF NOT EXISTS expense_payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
    method     TEXT    NOT NULL CHECK (method IN ('cash', 'qr')),
    amount     INTEGER NOT NULL CHECK (amount > 0)
);

CREATE INDEX IF NOT EXISTS idx_expense_payments_expense
    ON expense_payments (expense_id);

-- Backfill: every pre-existing expense version was paid fully in cash, so give
-- each row a single cash payment equal to its amount. This keeps historical
-- and current balances identical to before the schema change.
INSERT INTO expense_payments (expense_id, method, amount)
SELECT id, 'cash', amount FROM expenses;