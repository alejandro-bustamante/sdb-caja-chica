# AGENTS.md

Guidelines for any AI assistant (local LLM or otherwise) working on this
codebase. This project is a small desktop app (Python + Flet + SQLite) for
tracking sales, stock, expenses, and cash balance for a small shop. Full
context lives in `DESIGN.md` — read it before making non-trivial changes if
you haven't already.

## 1. The one rule that matters most

**Never write code that does `UPDATE` or `DELETE` on business data**
(products' prices, sales, sale items, sale payments, expenses, batches,
stock movements, debt payments, cash counts).

Every "edit" must be implemented as:
1. Insert a new row with the same `logical_id` and `version + 1`.
2. Set `superseded_at` on the previous version.

Every "delete" must be implemented as a new version with `deleted_at` set —
never an actual `DELETE FROM`.

If you find yourself about to write `UPDATE table SET ... WHERE id = ?` on
one of these tables, stop — that is very likely the wrong approach. The only
tables that may use plain `UPDATE` are non-business/reference tables like
`users` (e.g. toggling `active`) or `schema_version`.

Stock and money must never be stored as a value you overwrite. They are always
derived by summing the relevant ledger tables (`stock_movements`, sales,
payments, expenses) at query time. Do not introduce a cached "current stock"
or "current balance" column that gets updated in place — this reintroduces
exactly the failure mode (silent, unrecoverable data drift) the app exists to
prevent.

## 2. Do not use an ORM

This project intentionally uses raw `sqlite3` with a thin repository layer
(one module per entity under `db/repositories/`), not SQLAlchemy ORM or
similar. Do not introduce one, even to "simplify" something — the explicit
SQL is what keeps the append-only invariant enforceable and auditable. If a
repository function is getting hard to read, refactor within plain SQL/Python,
not by introducing an object-relational mapper.

## 3. Language convention — follow exactly

- **UI-facing text** (labels, buttons, messages the shop user reads): **Spanish**.
  Keep it in the centralized strings module (`ui/strings_es.py` or equivalent),
  not scattered as literals inside view code.
- **Everything else** — variable/function/table/column names, comments,
  commit messages, docstrings, error logs, this file, and any other
  documentation: **English**.
- Never mix the two within the same layer. If you're writing a DB column name
  or a Python identifier and you're tempted to write it in Spanish, it's
  wrong — rename it in English and put the Spanish only in the string that
  gets shown on screen.

## 4. Every write must be inside an explicit transaction

Any operation that touches more than one table (e.g. creating a sale +
its items + its payments + stock movements) must be wrapped in a single
transaction so it either fully commits or fully rolls back. Never leave a
sale with items but no payments, or a batch with items but missing stock
movements, as a possible intermediate state.

## 5. Snapshots vs. references — know which one you're using

- `sale_items.unit_price_applied` is a **snapshot**: it must never change
  after the sale, even if the product's catalog price changes later. Do not
  "helpfully" join against `product_prices` to compute historical sale totals
  — use the stored snapshot.
- `batches.expense_id` and similar foreign keys are **references**: they
  point at the current expense record's `logical_id`, not a copy of its data.

When adding a new field, decide explicitly which one it should be, and match
existing patterns in the schema rather than guessing.

## 6. User attribution

Every business-data write function must accept and store the acting user
(the currently selected app user, not inferred or defaulted). Never write a
sale, expense, batch, or debt payment without an explicit user argument. When
reassigning a record to a different user, this is a new version — do not
overwrite `registered_by_user`/original user on the existing row.

## 7. UI/UX behavior to preserve

- The current user must remain visibly displayed at all times (not just at
  login) — do not remove or shrink this indicator when adjusting layouts.
- The available balance must remain the single most prominent number on the
  main screen.
- The manual price override on a sale line must stay a secondary/hidden
  control (not a default-visible field) — it's intentionally low-visibility
  to avoid accidental edits, per `DESIGN.md` §3.3.
- The "mark debt as fully paid" action must remain a single, fast, one-click
  action. Partial payment ("abono") may require one extra step, but must
  never be blocked or removed — some users legitimately need it.
- Do not add shift/schedule concepts to the UI or data model — this is an
  explicit non-goal (see `DESIGN.md` §3.6, §7).
- Do not add product cost/margin/profit fields or calculations — explicit
  non-goal (see `DESIGN.md` §3.1, §7).

## 8. Database file / schema changes

- Any schema change must go through a new numbered file in
  `db/migrations/`, applied via the `schema_version` mechanism — never edit
  `schema.sql` and expect existing local `.db` files to pick up the change.
- Do not implement an automatic yearly (or any automatic time-based) database
  split. The only supported way to start a new ledger file is the explicit
  "Archive and start a new ledger" action described in `DESIGN.md` §3.9.

## 9. When scope is ambiguous

This app is intentionally small and not meant to grow into a general
platform. If a request seems to call for a feature beyond what's in
`DESIGN.md` (customer accounts, multi-user auth, cost/margin tracking,
reporting/analytics beyond the four Excel sheets, cross-file historical
queries), implement the smallest thing that satisfies the immediate need and
flag the scope question rather than building out generalized infrastructure
speculatively.

## 10. Before submitting a change

Sanity-check against this list:

- [ ] No `UPDATE`/`DELETE` on business tables — only new versions / soft
      deletes.
- [ ] No mutable "current stock" / "current balance" columns introduced.
- [ ] No ORM introduced.
- [ ] UI strings in Spanish, everything else in English.
- [ ] Multi-table writes wrapped in one transaction.
- [ ] Acting user recorded on every business-data write.
- [ ] Schema changes shipped as a new migration, not an edit to existing
      migrations or ad-hoc `schema.sql` changes.
