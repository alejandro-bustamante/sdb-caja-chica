# Implementation Plan #1 — Foundations, Schema, and Core Repositories

## Status of this document

This is the **first** implementation plan for the Small Shop Sales Ledger
project. It translates `DESIGN.md` and `AGENTS.md` into an ordered, checkable
sequence of concrete engineering tasks. It does **not** re-litigate any
decision already made in `DESIGN.md` — if something here seems to conflict
with `DESIGN.md` or `AGENTS.md`, those two files win and this plan is wrong.

**Audience**: an LLM coding agent with direct repository access, working
autonomously or semi-autonomously through the tasks below. Read `DESIGN.md`
and `AGENTS.md` in full before starting Task 0.

**Scope of this plan**: get the project from an empty repository to a
working, testable backend (schema, migrations, connection layer, and the
full repository layer for every entity) plus a minimal smoke-test UI shell
that proves the stack boots end to end. It intentionally stops **before**
building out the real UI screens and the Excel export — those are follow-up
plans (see "Out of scope" at the end).

**Language convention reminder (do not violate)**: all code, identifiers,
comments, docstrings, commit messages, and this plan itself are in English.
Any string the shop user will read is Spanish and lives only in
`ui/strings_es.py`. See `AGENTS.md` §3.

---

## Task 0 — Project scaffolding

1. Initialize the repository with `uv`:
   - `pyproject.toml` targeting Python 3.11+ (confirm the minimum version
     Flet currently supports and pin to it).
   - Add dependencies: `flet`, `openpyxl`. Do **not** add any ORM
     (SQLAlchemy, peewee, etc.) or query builder — raw `sqlite3` only
     (stdlib, no extra dependency needed).
   - Add dev dependencies: `pytest`, `ruff` (or the linter of your choice —
     pick one and record the choice in this repo's README, do not leave it
     ambiguous).
2. Create the directory layout exactly as specified in `DESIGN.md` §6:
   ```
   app/
     db/
       schema.sql
       migrations/
       connection.py
       repositories/
     domain/
       balance.py
       validation.py
     services/
       excel_export.py
       backup.py
     ui/
       views/
       components/
       strings_es.py
     main.py
   pyproject.toml
   ```
3. Add a `tests/` directory at the repo root (mirroring `app/`'s structure)
   for unit and integration tests. Every repository function written in this
   plan must ship with tests in the same commit/PR that introduces it.
4. Add a minimal `README.md` (English) documenting: how to install with
   `uv sync`, how to run (`uv run flet run` or equivalent), how to run tests
   (`uv run pytest`), and where the SQLite file lives during local
   development (suggest a `./dev-data/` folder ignored by `.gitignore`, kept
   separate from the real `Documents/<AppName>/` path used in production —
   see Task 4).
5. Add `.gitignore` covering the venv, `__pycache__`, `dev-data/`, and any
   Flet build artifacts.

**Exit criteria**: `uv sync` succeeds; `uv run pytest` runs (even with zero
tests passing yet, it must not error out on collection).

---

## Task 1 — Schema design (`db/schema.sql`) and migration mechanism

1. Write `db/schema.sql` containing the **initial** full schema, covering
   every table in `DESIGN.md` §3:
   - `users` (id, name, active) — plain mutable table, per `AGENTS.md` §1.
   - `products` (id, name, active).
   - `product_prices` (id, product_id, price, valid_from, superseded_at,
     user, reason nullable).
   - `batches` (id, timestamp, user, expense_id nullable FK).
   - `batch_items` (id, batch_id, product_id, quantity).
   - `stock_movements` (id, product_id, quantity_delta signed, reason,
     source reference — e.g. sale_item_id or batch_item_id, nullable
     depending on origin, timestamp).
   - `sales` (id, logical_id, version, superseded_at, deleted_at, timestamp,
     registered_by_user, current_user, is_credit, customer_name nullable,
     customer_note nullable).
   - `sale_items` (id, sale_id, product_id, quantity, unit_price_applied,
     price_manually_overridden).
   - `sale_payments` (id, sale_id, method CHECK IN ('cash','qr'), amount).
   - `debt_payments` (id, sale_id, amount, timestamp, user).
   - `expenses` (id, logical_id, version, superseded_at, deleted_at,
     timestamp, user, description, amount).
   - `cash_counts` (id, timestamp, user, counted_cash, expected_cash,
     difference, note nullable).
   - `schema_version` (single-row or append-only table tracking applied
     migration numbers).
2. Enforce invariants at the schema level wherever SQLite allows it, not just
   in Python:
   - `CHECK` constraints for `method IN ('cash','qr')`, non-negative
     `quantity`, etc.
   - Foreign keys with `ON DELETE RESTRICT` (never `CASCADE` — cascading
     deletes on business data would violate the append-only invariant by
     proxy).
   - Do **not** add a trigger or constraint that mutates a row in place to
     "keep things in sync" — any consistency check belongs in the repository
     layer's explicit transaction, not in an SQLite trigger that hides a
     write.
3. Design the migration mechanism in `db/migrations/`:
   - Numbered files, e.g. `0001_initial.sql`, `0002_....sql`.
   - `connection.py` must, on startup, read `schema_version`, and apply any
     migration files with a number greater than the current version, in
     order, inside a transaction, updating `schema_version` after each
     successful one.
   - The very first migration (`0001_initial.sql`) should simply be the
     contents of `schema.sql` — from this point on, `schema.sql` is kept as
     a human-readable "current shape of the DB" reference, but the source of
     truth for any existing `.db` file is the migration sequence. Document
     this clearly in a comment at the top of `schema.sql`.
4. Write `db/connection.py`:
   - A function to open a connection with the required PRAGMAs from
     `DESIGN.md` §5.2 (`journal_mode=WAL`, `foreign_keys=ON`,
     `synchronous=FULL`).
   - A context-manager-style transaction helper (e.g.
     `with transaction(conn) as cur: ...`) that commits on success and rolls
     back on any exception. This helper is what every repository function
     in Task 2 must use for multi-table writes (`AGENTS.md` §4).
   - The migration-runner function described above, called once at app
     startup before any repository code runs.

**Exit criteria**: a test that creates a fresh temp SQLite file, runs the
migration runner, and asserts `schema_version` matches the latest migration
and all expected tables exist.

---

## Task 2 — Repository layer (`db/repositories/`)

Build one module per entity. Every function must:
- Take an explicit `user` argument for any business-data write (`AGENTS.md`
  §6) — never infer or default it.
- Use the transaction helper from Task 1 for any multi-table write
  (`AGENTS.md` §4).
- Never emit `UPDATE`/`DELETE` against a business table (`AGENTS.md` §1) —
  only inserts of new versions / soft-delete rows, except where this plan
  explicitly says otherwise (the `users` table only).

Suggested function-level breakdown (adjust naming as needed, but keep the
"one verb, one responsibility" shape — do not fold multiple operations into
one mega-function):

### 2.1 `repositories/users.py`
- `create_user(conn, name) -> user_id`
- `list_active_users(conn) -> list[User]`
- `set_user_active(conn, user_id, active: bool)` — this is the one
  legitimate plain `UPDATE`, per `AGENTS.md` §1.

### 2.2 `repositories/products.py`
- `create_product(conn, name, initial_price, user) -> product_id` — creates
  the product row plus its first `product_prices` row in one transaction.
- `list_active_products(conn) -> list[ProductWithCurrentPrice]` (join against
  the latest non-superseded `product_prices` row).
- `update_product_price(conn, product_id, new_price, user, reason=None)` —
  inserts a new `product_prices` row, sets `superseded_at` on the previous
  one. Never touches the old row's price value.
- `set_product_active(conn, product_id, active: bool, user)` — decide
  explicitly whether "active" toggling is itself versioned or a simple flag;
  recommend treating it as a simple mutable flag on `products` (it's a
  visibility toggle, not a business fact being corrected), but flag this
  decision explicitly in the PR description for review rather than silently
  picking one.

### 2.3 `repositories/batches.py`
- `create_batch(conn, items: list[(product_id, quantity)], expense_amount,
  expense_description, user) -> batch_id` — single transaction that:
  1. Inserts the `expenses` row (version 1) for the restock cost.
  2. Inserts the `batches` row referencing that expense's `logical_id`.
  3. Inserts one `batch_items` row per item.
  4. Inserts one positive `stock_movements` row per item.
- Batches are logistical-only per `DESIGN.md` §3.2 — do not add a price/cost
  field to `batch_items`.

### 2.4 `repositories/sales.py`
- `create_sale(conn, items, payments, is_credit, customer_name, customer_note,
  user) -> sale_id` — single transaction that:
  1. Validates (via `domain/validation.py`, Task 3) that
     `sum(payments) == sum(item.quantity * item.unit_price_applied)`, unless
     `is_credit` is true, in which case `payments` must be empty.
  2. Inserts `sales` (version 1), `sale_items`, `sale_payments` (if any),
     and one negative `stock_movements` row per item.
- `edit_sale(conn, logical_id, ...same fields..., user) -> new_sale_id` —
  inserts a full new version (new row, `version = old.version + 1`), sets
  `superseded_at` on the previous version, and re-derives the stock
  movements: reverse the old version's movements and insert new ones for the
  new version so the net stock effect of that `logical_id` always reflects
  only its current version. Do this explicitly and readably — do not try to
  "diff" old vs new items to minimize row count; clarity beats cleverness
  here, and the invariant compliance rule matters more than row count.
- `void_sale(conn, logical_id, user) -> new_sale_id` — inserts a new version
  with `deleted_at` set, and reverses that logical_id's stock movements.
- `reassign_sale_user(conn, logical_id, new_current_user, acting_user) ->
  new_sale_id` — new version with `current_user` changed;
  `registered_by_user` copied unchanged from the previous version.
- `get_sale_current(conn, logical_id)` / `get_sale_history(conn, logical_id)`
  — read helpers.

### 2.5 `repositories/debts.py`
- `list_open_debts(conn)` — sales where `is_credit=true` and
  `sum(debt_payments) < sale total`.
- `mark_debt_paid(conn, sale_logical_id, user) -> payment_id` — inserts one
  `debt_payments` row for the full remaining balance. This must be reachable
  in the UI as a single action later (`AGENTS.md` §7) — keep the function
  itself equally simple (one call, no extra required arguments beyond
  `user`).
- `record_partial_payment(conn, sale_logical_id, amount, user) ->
  payment_id` — validates `amount <= remaining_balance` in
  `domain/validation.py`.

### 2.6 `repositories/expenses.py`
- `create_expense(conn, description, amount, user) -> expense_id`
- `edit_expense(conn, logical_id, description, amount, user) ->
  new_expense_id` — same versioning pattern as sales.
- `void_expense(conn, logical_id, user) -> new_expense_id`

### 2.7 `repositories/cash_counts.py`
- `record_cash_count(conn, counted_cash, user, note=None) -> cash_count_id`
  — computes `expected_cash` at insertion time (via `domain/balance.py`,
  Task 3), stores both `expected_cash` and `difference` as part of the
  snapshot row. Never recompute or "fix" a past `cash_counts` row.

**Exit criteria**: every function above has at least one passing test
covering the happy path, and at least one test asserting the append-only
invariant (i.e. asserting the old row still exists unchanged, with
`superseded_at`/`deleted_at` set as expected, after an edit/void).

---

## Task 3 — Domain logic (`domain/`)

### 3.1 `domain/balance.py`
Pure functions, no I/O beyond taking an open `conn`/cursor and running
`SELECT`s — no writes here:
- `compute_available_cash(conn, as_of=None) -> Decimal`
- `compute_available_qr(conn, as_of=None) -> Decimal`
- `compute_total_available(conn, as_of=None) -> Decimal`
- `compute_current_stock(conn, product_id) -> int`
- `compute_expected_cash(conn) -> Decimal` (used by `record_cash_count`)

Follow the formula in `DESIGN.md` §3.8 exactly. Use `Decimal`, not `float`,
for all money arithmetic to avoid rounding drift — confirm SQLite storage
strategy for money (recommend storing amounts as integer cents rather than
`REAL`, to sidestep floating-point issues entirely; if you take this route,
apply it consistently across the schema from Task 1 rather than mixing
representations).

### 3.2 `domain/validation.py`
- `validate_sale_payments(items, payments, is_credit)` — raises a clear,
  typed exception (not a bare `ValueError` with a string only) if the sum
  doesn't match, or if a non-credit sale has zero payments, or if a credit
  sale has any payments.
- `validate_partial_payment(amount, remaining_balance)`.
- Keep these framework-agnostic (no Flet imports here) so they're reusable
  from both the repository layer and any future non-UI context (e.g. tests,
  Excel import if ever added).

**Exit criteria**: unit tests for each validator covering at least one valid
and one invalid case per rule.

---

## Task 4 — Minimal app shell (`main.py`, `ui/`)

This task is intentionally small: prove the stack boots, not build the real
UI (that is a later plan).

1. `main.py`:
   - Resolves the DB file path under `Documents/<AppName>/<ledger-file>.db`
     per `DESIGN.md` §5.3 (make the app name and default filename constants,
     not hardcoded in multiple places).
   - Runs the migration mechanism from Task 1 against that path on startup.
   - Launches a minimal Flet app with:
     - A mandatory user picker (reads `users` via `repositories/users.py`;
       if none exist, offer a way to create the first one).
     - After picking a user, a placeholder main screen showing only: the
       persistent current-user indicator bar, and the computed total
       available balance (via `domain/balance.py`) — this proves the two
       UI/UX invariants from `AGENTS.md` §7 are wired end to end, before any
       other screen exists.
2. `ui/strings_es.py`: create the file now, even if it only has a handful of
   entries so far (user picker prompt, balance label). Every UI string
   added from here onward — in this task and all future ones — goes here,
   never as an inline literal in a view file (`AGENTS.md` §3).
3. `ui/components/`: extract the current-user indicator bar and the balance
   banner as their own reusable components now, since `AGENTS.md` §7
   requires both to persist across every future screen — building them as
   shared components from the start avoids having to retrofit every
   subsequent view.

**Exit criteria**: `uv run flet run` boots to the user picker, and after
selecting a user, shows the indicator bar and a balance of 0 (or whatever a
freshly migrated empty DB computes) without errors.

---

## Task 5 — CI skeleton

Do not build the full packaging/QEMU verification pipeline yet (that belongs
in a later plan, once there's an actual UI to verify) — but add a first
GitHub Actions workflow now so regressions are caught from day one:

- Workflow triggered on push/PR.
- Runs on `windows-latest` (per `DESIGN.md` §5, since that's the deploy
  target and the earliest point to catch Windows-specific issues).
- Steps: checkout, install `uv`, `uv sync`, `uv run pytest`.
- Do not yet add `flet build windows` or the QEMU verification step — flag
  those explicitly as follow-up work for the packaging plan.

**Exit criteria**: workflow passes on a trivial commit.

---

## Definition of done for this plan

- [ ] Task 0–5 exit criteria all met.
- [ ] `AGENTS.md` §10 checklist passes for every commit made under this plan.
- [ ] No table other than `users`/`schema_version` has been written to with
      a plain `UPDATE` or `DELETE` anywhere in the codebase (grep for
      `UPDATE ` and `DELETE FROM` against every business table name as a
      final check before considering this plan complete).
- [ ] Every repository write function has a test asserting the previous
      version/row is still present and unchanged after an edit or void.

## Out of scope for this plan (future plans)

- Real UI screens for sales entry, catalog, expenses, debts, cash count, and
  export (Task 4 only builds a placeholder shell).
- `services/excel_export.py` implementation (`DESIGN.md` §4).
- `services/backup.py` implementation (on-demand file-copy backup).
- The "Archive and start a new ledger" action (`DESIGN.md` §3.9).
- `flet build windows` packaging and the QEMU verification step
  (`DESIGN.md` §5, CI/packaging row).
- The hidden manual price-override control on sale lines (needs a real sale
  entry screen to exist first).
