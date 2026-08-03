# Non-Negotiable Criteria — Extracted Checklist

Source of truth: `AGENTS.md` and `DESIGN.md` at the project root. This file exists so the reviewer
doesn't have to re-derive or re-interpret the rules on every review — treat the wording here as
authoritative for review purposes, and re-read the source docs only if something here seems to
have drifted from them.

Each item below includes: the rule, why it exists, and concrete things to grep/check for.

---

## 1. Append-only business data — no `UPDATE`/`DELETE`

**Rule** (AGENTS.md §1): Never write `UPDATE` or `DELETE` against business data: product prices,
sales, sale items, sale payments, expenses, batches, stock movements, debt payments, cash counts.
Every edit = new row with same `logical_id`, `version + 1`, and `superseded_at` set on the
previous version. Every delete = new version with `deleted_at` set.

**Allowed exceptions**: plain `UPDATE` only on non-business/reference tables — `users` (e.g.
toggling `active`) and `schema_version`. Nothing else.

**Why**: this is the entire point of the app — making accidental, unrecoverable data loss
structurally impossible, not just discouraged by convention.

**Check for**:
- Any `UPDATE table SET` or `DELETE FROM table` where `table` isn't `users` or `schema_version`.
- A repository "edit" function that doesn't insert a new row.
- A "delete" function that removes a row instead of setting `deleted_at`.
- Missed `superseded_at` update on the prior version when inserting a new one (an edit that
  creates a new version without closing out the old one breaks "current state = latest
  non-deleted version").

---

## 2. No mutable stock/balance counters

**Rule** (DESIGN.md §2, AGENTS.md §1): Stock and money are never stored as values that get
overwritten. Current stock = sum of `stock_movements` for a product. Available cash/QR/balance is
always computed at query time from sales, payments, debt collections, and expenses — never cached
as a mutable stored value.

**Why**: a cached total that can silently drift from the ledger it's supposed to summarize
reintroduces the exact failure mode (undetectable data corruption) the append-only design exists
to prevent.

**Check for**:
- Any column that looks like `current_stock`, `balance`, `total_available`, etc. that is written
  to directly (not read via aggregate query).
- Any "correction" to stock that isn't itself a new signed `stock_movements` row with a reason.
- Balance formula in code should match DESIGN.md §3.8:
  ```
  available_cash = cash_sales + collected_debt_payments(cash portion) − expenses
  available_qr   = qr_sales
  total_available = available_cash + available_qr − expenses
  ```
  Verify any reimplementation of this formula matches semantically, including that expenses are
  subtracted once (not double-subtracted from both cash and total, unless that's the intended
  reading — check DESIGN.md if ambiguous rather than assuming).

---

## 3. No ORM

**Rule** (DESIGN.md §5.1, AGENTS.md §2): Raw `sqlite3` + thin repository layer only. No
SQLAlchemy ORM or similar, even to "simplify" a hard-to-read repository function.

**Why**: an ORM's mutable in-memory objects with implicit `UPDATE`-on-attribute-mutation work
directly against the append-only invariant — it becomes easy to accidentally bypass versioning by
just setting an attribute.

**Check for**: new dependencies in `pyproject.toml` that are ORMs; import statements for
SQLAlchemy or similar; any object pattern where mutating a Python attribute is expected to persist
to the DB.

---

## 4. Explicit transactions for multi-table writes

**Rule** (DESIGN.md §5.2, AGENTS.md §4): Any operation touching more than one table (sale + items
+ payments + stock movements; batch + items + stock movements) must be wrapped in a single
transaction — full commit or full rollback, no partial-write intermediate state ever observable.

**Check for**:
- A write function that opens multiple separate implicit transactions (e.g. multiple
  `conn.commit()` calls) instead of one span.
- An early `return` or unhandled exception between the first and last write in a multi-table
  operation that would leave a partial state committed.
- Confirm `PRAGMA foreign_keys = ON` and `synchronous = FULL` assumptions aren't being worked
  around.

---

## 5. User attribution on every business write

**Rule** (DESIGN.md §3.6, AGENTS.md §6): Every sale, expense, batch, debt payment write function
must accept and store the acting user as an explicit argument — never inferred, never defaulted,
never read from a global. Reassignment to a different user is a new version; the original
`registered_by_user`/timestamp on prior versions must remain visible in history, never overwritten.

**Check for**: optional user parameters with a default; user pulled from a module-level/global
"current user" inside the repository layer instead of passed in by the caller; a reassignment
implemented as an `UPDATE` on the existing row instead of a new version.

---

## 6. Snapshots vs. references

**Rule** (DESIGN.md §3.3, AGENTS.md §5): `sale_items.unit_price_applied` is a snapshot — must
never change after the sale even if catalog price changes later; never recompute historical sale
totals by joining against current `product_prices`. `batches.expense_id` and similar are
references (pointers to a `logical_id`), not copies of the pointed-to data.

**Check for**: any query that computes a historical sale total via `product_prices` instead of the
stored `unit_price_applied`; any new field — decide explicitly whether it's a snapshot or a
reference and confirm the implementation matches that choice.

---

## 7. Language boundary

**Rule** (DESIGN.md §5.4, AGENTS.md §3): UI-facing text (labels, buttons, messages) in Spanish,
centralized in the strings module (e.g. `ui/strings_es.py`). Everything else — code, identifiers,
comments, schema, docs, commit messages — in English. Never mixed within the same layer.

**Check for**: Spanish string literals inline in view code instead of routed through the strings
module; English UI-facing copy that should be Spanish; Spanish table/column/variable/function
names anywhere in the DB or Python layer.

---

## 8. Migrations, not ad-hoc schema edits

**Rule** (DESIGN.md §5.2/§6, AGENTS.md §8): Schema changes ship as a new numbered file under
`db/migrations/`, applied via the `schema_version` mechanism. Never edit `schema.sql` directly
expecting existing `.db` files to pick up the change; never edit an existing migration file after
the fact.

**Check for**: a diff that touches `schema.sql` without a corresponding new migration file; a diff
that modifies an already-existing migration file's content instead of adding a new one.

---

## 9. UX invariants

**Rule** (AGENTS.md §7):
- Current user indicator visible at all times, not just at login — never removed/shrunk.
- Available balance remains the single most prominent number on the main screen.
- Manual price override on a sale line stays a secondary/hidden control (icon or context menu),
  never a default-visible field.
- "Mark debt as fully paid" stays a single one-click action; partial payment (abono) may need one
  extra step but must never be blocked or removed.

**Check for**: layout changes that shrink/hide the user bar or demote the balance number visually;
a price override that becomes a default-visible input; a debt payment flow that adds friction to
the full-payment fast path or removes/gates the partial-payment path.

---

## 10. Explicit non-goals (scope discipline)

**Rule** (DESIGN.md §7, AGENTS.md §9): No cost/margin/profit tracking. No customer database or
auth beyond a name-only user picker. No shift/schedule modeling or enforcement. No automatic
time-based DB split (only the explicit "Archive and start a new ledger" action). No
general-purpose reporting/analytics beyond the four Excel export sheets. No multi-user concurrency
handling beyond what SQLite+WAL already provides.

**Check for**: any new field/table/computation that implies cost or margin; any authentication
mechanism beyond the existing user picker; any shift/schedule concept in data model or UI; any
automatic, time-triggered database splitting logic; any new report/analytics view beyond Sales,
Expenses, Debts, Balance summary.

**Note**: this is a floor for flagging, not an automatic rejection — if the user has explicitly
asked in the current conversation to expand scope, note it under "Out of scope / flagged for the
user" in the report rather than blocking it outright, since a deliberate, explicit scope decision
by the human is different from silent scope creep by an implementer LLM.
