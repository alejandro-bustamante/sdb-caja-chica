# Small Shop Sales Ledger — High-Level Design

## 1. Purpose and Context

This is a desktop application for a small side business (a small shop generating
petty cash), replacing a spreadsheet-based workflow. The spreadsheet approach works
functionally but has a critical weakness: users occasionally modify or delete data
or formulas by accident, and by the time the mistake is noticed, recovering the
original state is difficult or impossible.

The application does **not** aim to add business features beyond what the shop
already does on spreadsheets. Its value is:

1. A real database with a **complete history** of every record.
2. A design that makes accidental data loss **structurally very hard**, while still
   letting users correct legitimate mistakes with minimal friction.
3. Auditability: every sale, expense, restock, and debt payment is traceable to who
   did it and when, including every edit.

**Design priorities, in order:**
1. Data correctness and auditability — no exceptions.
2. Low-friction, intuitive daily use — the app must adapt to how the user already
   works, not the other way around. A missing optional detail is preferable to a
   workflow that annoys the user.
3. Clean, simple, modern desktop UI. Not a priority: responsiveness beyond keeping
   the layout usable across different monitor sizes.

The most important single number the app must always show clearly is **the amount
of money currently available** (cash + QR + collected debts − expenses).
Everything else is secondary detail that should still be available, but not
competing visually with that number.

---

## 2. Core Design Principle: Append-Only History

The central design decision that makes "flexible but auditable" possible is that
**business data is never overwritten (`UPDATE`) or hard-deleted (`DELETE`)**.

Editable entities (sales, expenses) are stored as a sequence of **versions**:

- Each logical record has a stable `logical_id`.
- Editing a record inserts a **new row** with the same `logical_id`, an
  incremented `version`, and marks the previous version's `superseded_at`
  timestamp.
- "Deleting" a record is simply a new version with `deleted_at` set (soft delete).
- The "current" state of any record is its latest non-deleted version. The full
  edit history is free: it's just all rows sharing that `logical_id`, ordered by
  version.

Stock and money are **never stored as mutable counters**. Instead they are modeled
as **ledgers** (append-only movement logs):

- `stock_movements`: every restock batch and every sale appends a signed quantity
  movement. Current stock for a product = sum of its movements. Stock is never
  "corrected" by editing a number directly — a correction is itself a new
  movement with a reason.
- Available cash/QR/balance is **always computed** from the underlying tables
  (sales, payments, debt collections, expenses) at query time — never cached as a
  mutable stored value.

This means the invariant "nothing legitimate ever disappears silently" is
enforced by how data is written, not by UI restrictions or convention — which is
what makes the flexible-but-auditable requirement achievable.

---

## 3. Domain Model

### 3.1 Products & Pricing (decoupled from cost)

The app deliberately does **not** model product cost, margin, or profit — the
shop owner manages pricing/margin decisions outside the app. Products only need:

- `products`: id, name, active flag.
- `product_prices`: append-only price history per product — `product_id`, price,
  `valid_from`, `superseded_at`, `user`, optional `reason`. The "current price" is
  simply the latest row without a `superseded_at`. Prices can be changed at any
  time from the catalog screen; changes are versioned like everything else.

### 3.2 Restocking (batches)

A "lote" (restock batch) is purely logistical — it only affects stock, never
price or cost:

- `batches`: id, timestamp, user, optional `expense_id` (link to the expense that
  paid for it).
- `batch_items`: `batch_id`, `product_id`, `quantity`. Each item produces a
  corresponding positive `stock_movements` row.
- The money that left the cash register to pay for the batch is recorded as an
  ordinary row in `expenses` (see 3.5), linked back via `expense_id`. The batch
  itself carries no price/cost information.

### 3.3 Sales

A sale is a single transaction that can contain multiple products and can be
split across payment methods:

- `sales` (versioned header): `logical_id`, `version`, `superseded_at`,
  `deleted_at`, `timestamp`, `registered_by_user`, `current_user` (may differ
  from the registering user after a reassignment), `is_credit` (fiado flag),
  `customer_name` (required only when `is_credit` is true), `customer_note`
  (optional, free text).
- `sale_items`: `sale_id`, `product_id`, `quantity`, `unit_price_applied` (a
  **snapshot** at sale time, independent of later catalog price changes),
  `price_manually_overridden` (boolean flag).
- `sale_payments`: `sale_id`, `method` (`cash` | `qr`), `amount`. A sale can be
  split across both methods; the sum of `sale_payments` must equal the sale
  total (enforced in the repository layer, not just the UI). If `is_credit` is
  true, there are **no** `sale_payments` rows yet — no money has entered the
  register — but stock is still decremented via `stock_movements`.

**Hidden manual price override:** each product line in the sale form has an
unobtrusive secondary control (e.g. a small icon or context menu, not a visible
field by default) to override the price for that single line. This keeps the
common path frictionless while making the override intentional and clearly
marked in the data (`price_manually_overridden`).

### 3.4 Credit sales / debts ("fiado")

No formal customer entity is needed — just a required free-text name and an
optional note, with no validation on the content:

- A debt is simply a sale with `is_credit = true`. Outstanding balance for that
  sale = sale total − sum of its `debt_payments`.
- `debt_payments`: `sale_id`, `amount`, `timestamp`, `user`.
- **Default, fast path:** a single action ("mark as paid") inserts one payment
  row for the full outstanding amount.
- **Secondary path:** partial payment ("abono") requires one extra step (e.g. an
  expandable amount field) but is fully supported — the user must never be
  blocked by the system if a partial payment is genuinely needed.

### 3.5 Expenses

Free-form and covers both restocking payments and any other planned or
unplanned expense:

- `expenses` (versioned like sales): `logical_id`, `version`, `superseded_at`,
  `deleted_at`, `timestamp`, `user`, `description`, `amount`. Description detail
  is entirely up to the user — as little or as much as they find useful.

### 3.6 Users / session

- `users`: id, name, active flag. **No passwords.** Expected to be 2–3 users.
- A mandatory user picker on app start, plus a **persistent, hard-to-miss
  indicator** (e.g. a colored top bar with the current user's name) shown across
  the whole app, so a user doesn't keep working under someone else's identity by
  mistake.
- Every record (sale, expense, batch, debt payment) stores the acting user.
  Reassigning a sale to a different user creates a new version with a different
  `current_user`; the original `registered_by_user` and timestamp remain visible
  in history.
- Shifts have fixed nominal schedules in real life, but shift assignment is
  informal and flexible (someone may cover an unplanned shift). **The app does
  not model or enforce shifts** — it stays out of that organizational detail
  entirely.

### 3.7 Cash counts ("arqueo")

- `cash_counts`: timestamp, user, `counted_cash`, `expected_cash` (computed at
  that moment), `difference`, optional note.
- This is a **snapshot**, never a retroactive correction. If there's a
  discrepancy, it is recorded as such — the system never silently reconciles it.

### 3.8 Available balance (the most important number)

Always computed, never stored as a mutable value:

```
available_cash = cash_sales + collected_debt_payments(cash portion...) − expenses
available_qr   = qr_sales
total_available = available_cash + available_qr − expenses
```

Cash and QR are tracked separately (needed for the cash count to be meaningful),
and expenses (including restocking) are subtracted from the total. This
computed balance is the single most prominent element of the main screen.

### 3.9 Data file lifecycle

A single continuous SQLite file is used — **no automatic yearly split**. Instead,
there is one explicit action in the app menu: **"Archive and start a new
ledger"**, which:

1. Leaves the current database file untouched in its folder.
2. Creates a new, empty database file.
3. Switches the running app to the new file, seamlessly, without needing a
   restart.

The app never needs to read archived files; if historical data is ever needed,
the old file can be opened manually outside the app (e.g. with any SQLite
browser, or a future read-only "open archived ledger" feature if it becomes
useful).

---

## 4. Excel Export

A single export screen with a **date range picker** (no fixed daily/weekly
shortcuts) producing a workbook with these sheets, all filtered to the chosen
range:

1. **Sales** — one row per sale item (or per sale, with payment breakdown
   columns), including product, quantity, unit price applied, payment
   method(s)/amounts, credit flag, customer name if credit.
2. **Expenses** — description, amount, timestamp, user, whether linked to a
   restock batch.
3. **Debts** — customer name, note, sale total, amount paid, outstanding
   balance, status (open/settled).
4. **Balance summary** — totals for the selected range: cash sales, QR sales,
   debts collected, expenses, and net available balance.

---

## 5. Technology Stack

| Concern | Choice |
|---|---|
| Language | Python |
| UI framework | Flet |
| Package manager | `uv` (as recommended by Flet) |
| Database | SQLite (local file), accessed via raw `sqlite3` + a thin repository layer (**no full ORM** — see rationale below) |
| Excel export | `openpyxl` (or similar) |
| Target platform | Windows (deployed), developed on Arch Linux |
| CI / packaging | GitHub Actions on a `windows-latest` runner, running `flet build windows` |
| Verification | Minimal Windows QEMU VM to run the built `.exe` before release |

### 5.1 Why not a full ORM

An ORM built around mutable in-memory objects (e.g. SQLAlchemy's ORM layer with
its identity map and implicit `UPDATE` on attribute mutation) works against the
central invariant of this design: "editing" must mean "insert a new version,"
never "mutate a row in place." Using a full ORM makes it easy — for a human or
an LLM assistant working on the code — to accidentally bypass that invariant by
just setting an attribute.

Given the low query complexity needed (no complex joins, no reporting engine —
this app doesn't need anything a spreadsheet couldn't already compute), the
better fit is:

- Raw `sqlite3` (standard library) plus a **thin repository module per entity**
  (`create_sale`, `edit_sale`, `void_sale`, `collect_debt`, etc.), where each
  function embeds the "insert new version, mark previous superseded" logic
  explicitly in SQL.
- This keeps the invariant enforced by code structure rather than convention,
  keeps the SQL fully visible/auditable in the codebase itself, and avoids
  fighting an ORM abstraction that wasn't designed for an append-only model.

This satisfies both stated priorities: **robustness first** (the invariant is
structurally guaranteed, not just hoped for) and **fast iteration second** (a
handful of tables, explicit and readable SQL, no ORM mapping/migration
boilerplate to maintain).

### 5.2 SQLite configuration

Robustness and safe transactional behavior take priority over raw performance
(data volume is small):

- `PRAGMA journal_mode = WAL`
- `PRAGMA foreign_keys = ON`
- `PRAGMA synchronous = FULL`
- Every write operation (sale, expense, batch, debt payment, price change) runs
  inside an explicit transaction; the repository layer never leaves partial
  writes possible.
- A `schema_version` table plus a small set of numbered migration scripts,
  applied automatically on app startup. This is needed even without an annual
  DB split, since the app itself may be updated mid-year while the same
  database file stays active.
- On-demand backup command (simple file copy of the SQLite file) — no automatic
  backup schedule needed, given the single-user, low-volume context.

### 5.3 Database file location

Stored under the user's Documents folder, in a dedicated subfolder created by
the app (e.g. `Documents/<AppName>/<ledger-file>.db`).

### 5.4 Language convention

- **UI text** (everything the end user sees): **Spanish**.
- **Everything else** — code, comments, database schema (table/column names),
  commit messages, internal documentation: **English**.
- Practically: UI strings live in one clearly separated layer (e.g. a small
  dictionary/module of Spanish labels bound to Flet widgets), so the
  English/Spanish boundary is unambiguous and there is never a need to guess
  which language a given identifier should be in.

---

## 6. Suggested Project Structure

A flat, low-boilerplate layout appropriate for a project that is not expected to
grow indefinitely in scope:

```
app/
  db/
    schema.sql          # table definitions, versioned via migrations/
    migrations/         # numbered migration scripts
    connection.py       # connection setup, PRAGMAs, transaction helper
    repositories/        # one module per entity: sales.py, expenses.py,
                          # batches.py, debts.py, products.py, cash_counts.py
  domain/
    balance.py          # pure balance/stock calculation logic
    validation.py       # e.g. payment amounts sum to total, required fields
  services/
    excel_export.py
    backup.py
  ui/
    views/              # one Flet view per screen (sales, catalog, expenses,
                          # debts, cash count, export)
    components/         # shared widgets (user indicator bar, balance banner)
    strings_es.py       # all user-facing Spanish text, centralized
  main.py
pyproject.toml           # managed by uv
```

No separate "use case" layer beyond `domain/` is introduced, since the
repositories already express the operations directly and an extra
indirection layer would add complexity without a corresponding benefit at
this scope.

---

## 7. Explicit Non-Goals

To keep scope bounded, as discussed:

- No cost/margin/profit tracking.
- No customer database or authentication beyond a name-only user picker.
- No shift/schedule enforcement.
- No automatic yearly database split (replaced by an explicit manual
  "archive and start new ledger" action).
- No multi-user concurrent access considerations beyond what SQLite + WAL
  provides for a single local desktop user.
- No general-purpose reporting/analytics beyond the four Excel export sheets.

---

## 8. From Here

This document is the stable reference for scope and data model. Implementation
plans (schema DDL, migration scripts, screen-by-screen UI specs, CI pipeline
setup) should be written as separate, more specific documents that build on
top of the model and invariants defined here, without re-litigating them.
