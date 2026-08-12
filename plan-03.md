# Implementation Plan #3 — Export, Backup, Archiving, and Packaging

## Status of this document

This is the **third** implementation plan for the Small Shop Sales Ledger
project. It builds on Plan #1 ("Foundations, Schema, and Core Repositories")
and Plan #2 ("Daily-Use UI Screens"), both assumed complete: the six daily
screens (Ventas, Catálogo, Reponer stock, Gastos, Fiado, Arqueo) work end to
end against the shared repository/domain layer, with the persistent user
indicator and balance banner mounted once at the shell level.

Since Plan #2 landed, an additional migration —
`0003_expense_payments.sql` — was applied directly, ahead of any plan
document describing it. It adds an `expense_payments` table (mirroring
`sale_payments`: `expense_id`, `method` `cash`/`qr`, `amount`) so an expense
(including a restock batch's linked expense) can be paid partly or fully by
QR instead of always coming out of the cash drawer. That migration changed
the **schema** only — it did not by itself update the repository functions,
`domain/balance.py`, or the UI that were built against the old single-amount,
cash-only assumption. Bringing the rest of the codebase in line with that
schema change is the first and most important task of this plan (Task 1),
ahead of any of the originally-scoped Plan #3 work.

This plan does **not** re-litigate `DESIGN.md` or `AGENTS.md`. Where an
earlier plan left an explicit open decision for review (e.g. whether
`products.active` toggling is versioned or a plain flag), assume it was
already settled — read the existing code, don't re-decide it here.

**Scope of this plan**: (1) finish wiring `expense_payments` through the
repository, domain, and UI layers so the balance calculation is correct
again; (2) implement the pieces explicitly deferred by Plan #1 and Plan #2 —
Excel export, on-demand backup, "archive and start a new ledger", and
Windows packaging with QEMU verification.

**Audience**: same as the previous plans — an LLM coding agent with direct
repository access, working autonomously or semi-autonomously through the
tasks below. Read `DESIGN.md`, `AGENTS.md`, `plan-01.md`, `plan-02.md`, and
`0003_expense_payments.sql` in full before starting Task 0.

**Language convention reminder (do not violate)**: all code, identifiers,
comments, and this plan are in English. Every string the shop user reads is
Spanish and lives only in `ui/strings_es.py`. See `AGENTS.md` §3.

---

## Task 0 — Recap and verification before starting

1. Confirm Plan #2's exit criteria still hold on the current branch:
   `uv run pytest` passes, `uv run flet run` boots to the full shell with
   working navigation across all six screens.
2. Confirm `0003_expense_payments.sql` is the latest applied migration and
   `schema_version` reflects it.
3. Audit the **current, real** state of the following against the
   post-migration schema — do not assume from `plan-01.md`/`plan-02.md`
   wording, since both were written before `expense_payments` existed:
   - `repositories/expenses.py` — does `create_expense`/`edit_expense`
     still take a single `amount` and never write `expense_payments`?
   - `repositories/batches.py` — does `create_batch` still create an
     all-cash expense implicitly?
   - `domain/balance.py` — do `compute_available_cash`/
     `compute_available_qr` still subtract *all* expenses from cash only,
     regardless of how they were actually paid?
   - `ui/views/expenses.py` and `ui/views/restock.py` — do their forms still
     collect a single amount field with no method split?
4. Record in the tracking PR/commit exactly which of the above were already
   updated ad hoc since the migration landed (if any) versus which still
   need work. Task 1 below assumes the worst case (nothing updated yet);
   adjust its sub-tasks down if some pieces already exist rather than
   redoing them.

**Exit criteria**: a short note (first commit message, or a comment at the
top of the tracking PR) confirming the audit above was performed against
the real code.

---

## Task 1 — Bring expense writes and balance computation in line with `expense_payments`

This is the most important task in this plan. Until it's done,
`domain/balance.py` silently miscalculates the available balance for any
expense paid partly or fully by QR — exactly the kind of silent,
unrecoverable drift `DESIGN.md` §1 and `AGENTS.md` §1 exist to prevent. Treat
this task as blocking for everything else in this plan.

### 1.1 `domain/validation.py`

- Add `validate_expense_payments(amount, payments)`: raises a clear, typed
  exception (matching the style already used by `validate_sale_payments`) if
  `sum(p.amount for p in payments) != amount`, or if `payments` is empty.
  Unlike a credit sale, there is no "unpaid expense" concept in this app —
  every expense has at least one payment row — so do not add an
  `is_credit`-style bypass here.

### 1.2 `repositories/expenses.py`

- Change `create_expense(conn, description, amount, payments, user) ->
  expense_id`: single transaction that validates via
  `validate_expense_payments`, then inserts the `expenses` row (version 1)
  and one `expense_payments` row per payment.
- Change `edit_expense(conn, logical_id, description, amount, payments,
  user) -> new_expense_id`: same versioning pattern as before (new row,
  `version = old.version + 1`, `superseded_at` set on the previous one) —
  plus, new in this plan, insert a fresh set of `expense_payments` rows tied
  to the **new** `expense_id`. This exactly mirrors how `edit_sale` must
  re-insert `sale_payments` for its new version, since `expense_payments`
  references the physical row id, not the `logical_id`. The old version's
  `expense_payments` rows stay untouched, attached to the old (now
  superseded) `expense_id`, forming that version's permanent history — do
  not touch, move, or delete them.
- `void_expense`: confirm it does not need its own `expense_payments` rows
  (a voided version contributes nothing to the balance once 1.4 is fixed to
  filter on non-deleted current versions). While here, confirm that filter
  actually exists in the current balance queries — if it doesn't, that's a
  latent bug independent of migration 0003; fix it as part of this task and
  note it explicitly in the PR description as a bug fix, not scope creep.

### 1.3 `repositories/batches.py`

- Change `create_batch(conn, items, expense_amount, expense_payments,
  expense_description, user) -> batch_id` so a restock can be split
  cash/QR exactly like any other expense — a restock is paid for the same
  way anything else leaving the till is paid for. Route the expense side of
  this through the same `create_expense` logic from 1.2 rather than
  duplicating the insert, to avoid two slightly different code paths that
  both write `expenses`/`expense_payments`.
- No change needed to `resolve_batch_expense` / `find_batch_for_expense` —
  they resolve by `logical_id` and never touch payment rows directly.

### 1.4 `domain/balance.py`

Rewrite `compute_available_cash`, `compute_available_qr`,
`compute_total_available`, and `compute_expected_cash` to:

- Sum `sale_payments` by method, for current (non-superseded), non-deleted
  sale versions only — confirm this is already correct; it's the existing
  behavior this task must not regress.
- Sum `expense_payments` by method, for current, non-deleted expense
  versions only, using the same "current version" SQL pattern already used
  for sales — do not invent a second pattern for expenses.
- Subtract the QR expense sum from the QR sale sum, and the cash expense
  sum from the cash sale sum, instead of subtracting all expenses from cash.

`debt_payments` has no `method` column, and was never touched by migration
0003 — `DESIGN.md` §3.8's original formula already left this ambiguous
("collected debt payments (cash portion...)"). Decide explicitly now,
rather than silently picking one:

  - **(a)** Treat all debt collections as cash. Simplest, no schema change,
    and matches the likely real-world case (a fiado is usually settled in
    cash at the register).
  - **(b)** Add a `method` column to `debt_payments` via a new migration
    (`0004_debt_payments_method.sql`), mirroring `sale_payments` /
    `expense_payments`, and update `mark_debt_paid` /
    `record_partial_payment` to accept it.

  Flag this explicitly in the PR description either way — the same way
  Plan #1 flagged the `products.active` versioning decision. Default to
  **(a)** if no reviewer input is available before this task needs to ship,
  since it's the smaller change and requires no new migration; leave a
  `# TODO(reviewer): confirm debt payment method assumption` comment at the
  relevant line in `domain/balance.py` if you take this default.

- Update every existing test that asserts a specific balance number after
  an expense — earlier tests likely assumed cash-only expenses and will
  need fixtures with explicit payment splits now.

Task 1 is repository/domain-only; no UI changes here (see Task 2) so it can
be reviewed and merged independently of the UI work.

**Exit criteria**:
- A test creating a QR-paid expense confirms `compute_available_qr`
  decreases while `compute_available_cash` is unaffected, and vice versa
  for a cash-paid expense.
- A test creating a split cash/QR restock batch confirms both balances move
  correctly and by the right amounts.
- A test confirms `edit_expense` leaves the prior version's
  `expense_payments` rows untouched and still attached to the old version's
  id.
- The debt-payments-method decision is recorded in the PR description,
  either as "decided: (a)" with the TODO comment in place, or as "decided:
  (b)" with migration `0004` shipped.

---

## Task 2 — Shared payment-split UI component; update Expenses and Restock screens

Three screens (Ventas, Gastos, Reponer stock) now all need "one or two
amounts across cash/QR that must sum to a total." Extract the interaction
once instead of a third copy-paste.

1. Extract a shared `ui/components/payment_split.py` component (cash amount
   field, QR amount field, a live "remaining" hint, client-side sum check)
   out of the sales screen (Plan #2, Task 2.3) so `expenses.py` and
   `restock.py` can also mount it. This is a UI de-duplication only — the
   authoritative check stays server-side in `validate_expense_payments` /
   `validate_sale_payments`, unchanged by this task.
2. Update `ui/views/expenses.py`'s create/edit forms to use the shared
   component and pass `payments` through to `create_expense` /
   `edit_expense`.
3. Update `ui/views/restock.py`'s form the same way, passing
   `expense_payments` through to the new `create_batch` signature from
   Task 1.3.
4. Update the expenses list and the recent-batches list to show the
   payment breakdown (e.g. "Efectivo $X / QR $Y") instead of just the
   total. Add the new Spanish labels to `strings_es.py`.

**Exit criteria**: creating a split cash/QR expense and a split cash/QR
restock batch both work end-to-end in the UI, and the balance banner
reflects both immediately and correctly. Controller tests cover the shared
component's sum/remaining logic once; both screens' controller tests reuse
it rather than re-testing the same arithmetic twice.

---

## Task 3 — Excel export (`services/excel_export.py` + export screen)

Per `DESIGN.md` §4, unchanged in shape by migration 0003 except where noted
below.

1. `services/excel_export.py`:
   - `export_range(conn, date_from, date_to, output_path)` producing a
     workbook via `openpyxl` with four sheets, all filtered to the chosen
     range and to current, non-deleted versions only:
     - **Sales** — one row per sale item: product, quantity, unit price
       applied, payment method(s)/amounts (from `sale_payments`), credit
       flag, customer name if credit.
     - **Expenses** — description, amount, timestamp, user, payment
       method(s)/amounts (from `expense_payments` — this column set is new
       since migration 0003 and extends the original `DESIGN.md` §4.1
       wording; it's a natural companion to the existing "linked to
       restock" column), and the "linked to restock" badge resolved via
       `find_batch_for_expense` (Plan #2, Task 5) — reuse it, do not
       re-derive the join in the export code.
     - **Debts** — customer name, note, sale total, amount paid,
       outstanding balance, status (open/settled).
     - **Balance summary** — totals for the range: cash sales, QR sales,
       debts collected, cash expenses, QR expenses, net available balance —
       computed via the same `domain/balance.py` functions fixed in Task 1,
       so the export can never disagree with what the app shows on screen.
   - Convert stored integer cents to normal decimal currency figures only
     at the export boundary — the workbook should read naturally, not in
     cents.
2. `ui/views/export.py`: a single screen with a date-range picker (no fixed
   daily/weekly shortcuts, per `DESIGN.md` §4) and an "Exportar" button that
   calls `export_range`, writes to a user-chosen location via Flet's file
   picker, and shows a success/error message in Spanish.
3. Add this screen to the nav shell built in Plan #2, Task 1.

**Exit criteria**: exporting a range containing a cash sale, a QR sale, a
split sale, a credit sale, a plain expense, a batch-linked expense, an open
debt, and a settled debt produces a workbook whose four sheets match the
live in-app balance and lists for that same range. A controller test covers
date-range validation (`date_from <= date_to`, both required).

---

## Task 4 — Backup (`services/backup.py`)

1. `backup_database(source_path, backup_dir) -> backup_file_path`: a plain
   file copy of the current SQLite file into a timestamped filename inside
   `backup_dir`. Since the DB runs in WAL mode, run
   `PRAGMA wal_checkpoint(TRUNCATE)` on the source connection immediately
   before copying, so the backup file is self-contained and doesn't leave
   uncommitted WAL data behind.
2. Add a menu action ("Copiar respaldo") in the app shell that calls this
   and shows the resulting path in a confirmation message. No automatic
   schedule — this stays a manual, on-demand action per `DESIGN.md` §7.

**Exit criteria**: triggering the backup action while the app has an active
WAL file (i.e. right after a write, before any checkpoint) produces a
valid, independently-openable copy containing all current data.

---

## Task 5 — "Archive and start a new ledger" (`DESIGN.md` §3.9)

1. A menu action that:
   1. Leaves the current database file untouched in its folder.
   2. Creates a new, empty database file and runs the migration mechanism
      against it immediately (same path as first-run).
   3. Switches the running app's connection to the new file, without a
      restart.
2. Step 1.3 requires the app's connection/session state to be swappable at
   runtime. Confirm where `conn` currently lives (Plan #2, Task 0 asked the
   same question about session state — reuse that answer). If it's held in
   one place (shell/session state) and passed down, this is straightforward;
   if any view captured `conn` in a closure at construction time instead of
   reading it from shared session state on each use, that assumption breaks
   here and needs fixing. If fixing it touches most of the view layer, flag
   the scope of that refactor explicitly in the PR rather than doing it
   silently.
3. Require a confirmation dialog before archiving (Spanish copy in
   `strings_es.py`). This is not destructive — nothing is deleted — but it's
   easy to trigger by mistake and confusing if it happens silently.
4. After switching, the balance banner and every list screen must reflect
   the new (empty) ledger immediately. Reuse the existing
   `refresh_balance` / `on_change` plumbing from Plan #2, Task 1; extend it
   to a broader "reload everything" callback if `refresh_balance` alone
   isn't sufficient to refresh list screens that cached data locally.

**Exit criteria**: archiving creates a new file; the old file is
byte-for-byte unchanged on disk afterward; the app continues working
against the new file without a restart; manually reopening the old file
(e.g. with any SQLite browser) still shows all of its original data intact.

---

## Task 6 — Windows packaging and QEMU verification

Extends the CI skeleton from Plan #1, Task 5, which deliberately stopped
short of this.

1. Add a `flet build windows` step to the existing GitHub Actions workflow,
   producing the `.exe`.
2. Add a QEMU verification step per `DESIGN.md` §5: boot a minimal Windows
   QEMU VM, run the built `.exe`, and assert it launches to the user picker
   without error. Keep this a smoke check, not full UI automation —
   proportionate to the project's scope.
3. Document the QEMU setup (image source, boot script) in `README.md` so
   it's reproducible locally, not just in CI.

**Exit criteria**: a tagged commit produces a downloadable Windows `.exe`
artifact from CI, and the QEMU smoke step passes.

---

## Task 7 — Testing for this plan's new surfaces

1. Controller tests (no Flet) for: export date-range validation, the
   shared payment-split component's logic (tested once, reused by all
   three consuming screens' controller tests), and the archive
   confirmation flow's state handling.
2. Repository/domain tests for Task 1's balance fix — see Task 1's exit
   criteria; these are the most important tests in this plan.
3. One view-level smoke test for `export.py`, following the pattern
   established in Plan #2, Task 8 (build the root control against a
   freshly migrated temp SQLite connection and a fake session, assert no
   exception).

**Exit criteria**: `uv run pytest` passes with all of the above included.

---

## Task 8 — Manual QA pass

Append to the existing `MANUAL_QA.md` (created in Plan #2, Task 9) rather
than replacing it. Add sections for: split cash/QR expense entry, split
cash/QR restock entry, Excel export (including a step to manually open the
resulting file and check all four sheets by eye), backup, and archive-and-
new-ledger.

**Exit criteria**: `MANUAL_QA.md` covers every new or changed screen/action
from this plan, walked through at least once with results noted in the PR
description.

---

## Definition of done for this plan

- [ ] Task 0–8 exit criteria all met.
- [ ] `AGENTS.md` §10 checklist passes for every commit made under this
      plan.
- [ ] `domain/balance.py` correctly accounts for `expense_payments` by
      method — no QR-paid expense is ever subtracted from the cash balance,
      or vice versa.
- [ ] The `debt_payments` method question (Task 1.4) is explicitly recorded
      as decided in the PR description, not silently defaulted without a
      note.
- [ ] Excel export figures never disagree with the live balance banner for
      the same date range.
- [ ] The archive action never mutates or deletes the previous ledger file.
- [ ] The backup action produces a self-contained, valid copy even
      immediately after a write, with an active WAL file.
- [ ] No new `UPDATE`/`DELETE` on business tables introduced anywhere in
      this plan's code (`expense_payments` writes are inserts only, exactly
      like `sale_payments`).
- [ ] All new UI-facing strings live in `ui/strings_es.py`, none inline.

## Out of scope for this plan (future)

- A read-only "open archived ledger" viewer inside the app — `DESIGN.md`
  §3.9 mentions this only as a possible future feature, not a requirement.
- Any UI to reconcile or explain historical `cash_counts` discrepancies
  beyond what's already recorded — `DESIGN.md` §3.7 is explicit that there
  is never a "corregir" action, and this plan does not add one.
- Full UI automation testing beyond the smoke tests and manual QA checklist
  established across all three plans.
- Any packaging target other than Windows.
