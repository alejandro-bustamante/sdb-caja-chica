# Implementation Plan #2 — Daily-Use UI Screens

## Status of this document

This is the **second** implementation plan for the Small Shop Sales Ledger
project. It builds directly on Plan #1 ("Foundations, Schema, and Core
Repositories"), which is assumed complete and verified: schema through
migration `0002_batches_expense_reference.sql` is in place, `db/repositories/`
has full coverage for users, products, batches, sales, debts, expenses, and
cash_counts, `domain/balance.py` and `domain/validation.py` are implemented
and tested, and `main.py` boots to a placeholder screen with the user picker,
the persistent user indicator bar, and the balance banner (Plan #1, Task 4).

This plan does **not** re-litigate `DESIGN.md` or `AGENTS.md`. Where Plan #1
left an explicit open decision for review (e.g. whether `products.active`
toggling is versioned or a plain flag), this plan assumes Plan #1's
implementation already settled it — read the existing code, don't re-decide.

**Scope of this plan**: build the real, daily-use UI screens on top of the
existing repository/domain layer — sales entry (the core screen), catalog
management, restocking, expenses, debts ("fiado"), and cash counts
("arqueo") — replacing the Task 4 placeholder body with a proper navigation
shell while preserving its two non-negotiable invariants (persistent user
indicator, prominent balance). It intentionally stops **before** Excel
export, backup, "archive and start a new ledger", and Windows
packaging/QEMU verification — those remain for Plan #3 (see "Out of scope"
at the end).

**Audience**: same as Plan #1 — an LLM coding agent with direct repository
access, working autonomously or semi-autonomously through the tasks below.
Read `DESIGN.md`, `AGENTS.md`, and the current state of `app/db/` and
`app/domain/` before starting Task 0.

**Language convention reminder (do not violate)**: all code, identifiers,
comments, and this plan are in English. Every string the shop user reads is
Spanish and lives only in `ui/strings_es.py`. See `AGENTS.md` §3.

---

## Task 0 — Recap and verification before starting

1. Confirm Plan #1's exit criteria still hold on the current branch:
   `uv run pytest` passes, `uv run flet run` boots to the placeholder
   screen.
2. Re-read the current `db/repositories/*.py` and `domain/*.py` modules
   directly — do not assume their exact function signatures from
   `plan-01.md`; the code is the source of truth, the plan text is not. In
   particular, confirm:
   - How current-user/session state is represented and passed into
     `main.py`'s placeholder screen (Plan #1, Task 4) — reuse that same
     mechanism everywhere in this plan, don't invent a second one.
   - The exact signature of `resolve_batch_expense` in
     `repositories/batches.py` (per `AGENTS.md` §5a) and of `create_batch`.
   - Whether `products.active` toggling ended up versioned or a plain
     mutable flag (Plan #1, Task 2.2 flagged this as an open decision for
     review) — build the catalog UI against whatever was actually
     implemented.
3. If any of the above diverges from `plan-01.md`'s description, trust the
   code and proceed. Do not "fix" Plan #1's code to match the old plan text
   as part of this plan unless it's an actual bug.

**Exit criteria**: a short note (first commit message, or a comment at the
top of the tracking PR) confirming the above was checked against the real
code, not assumed from the plan text.

---

## Task 1 — Navigation shell

Replace the Task 4 placeholder body — **not** the user picker, **not** the
indicator bar, **not** the balance banner, those stay exactly as built —
with real navigation across the six screens this plan adds: Ventas,
Catálogo, Reponer stock, Gastos, Fiado, and Arqueo.

1. Add a persistent app-shell layout in `main.py` (or a new `ui/shell.py`
   if `main.py` is getting crowded — keep `main.py` itself thin):
   - `NavigationRail` (or `Tabs` — pick whichever fits the target desktop
     window size better per `DESIGN.md` §1 priority 3; do not over-engineer
     responsive behavior beyond "usable across different monitor sizes")
     switching a single content area between the six views below.
   - The user indicator bar and balance banner (`ui/components/`, built in
     Plan #1) are mounted **once**, at the shell level, above the
     nav/content area — never per-view. This is a structural guarantee, not
     a per-screen reminder, that `AGENTS.md` §7's persistence requirement
     can't be broken by a future screen forgetting to include them.
   - Balance banner recomputes (via `domain/balance.py`) on every
     navigation change and after every write action from any screen —
     define one shared `refresh_balance()` callback in the shell and pass
     it down, rather than having each view recompute independently.
2. Establish the view module contract used by all screens in this plan:
   - Each `ui/views/<name>.py` exposes a single
     `build(conn, session, on_change) -> ft.Control` function. `on_change`
     is the shell's `refresh_balance` (or a slightly richer callback if
     other shared state needs refreshing) — call it after any successful
     write.
   - Keep Flet widget construction and callback wiring in
     `ui/views/<name>.py`. Keep anything that decides *what* to show or
     *whether* an action is valid — formatting, computed labels, "is this
     button enabled" logic, message selection — in a sibling
     `ui/views/<name>_controller.py` with **no Flet imports**, so it is
     unit-testable without booting Flet. This pattern is new in this plan;
     Plan #1 didn't need it since Task 4 was a placeholder.

**Exit criteria**: `uv run flet run` boots to the user picker, then to a
shell with working navigation between six empty (or stub) screens, with the
indicator bar and balance banner both visible and correct on every screen.

---

## Task 2 — Sales entry screen (`ui/views/sales.py`)

The single most-used screen; keep the happy path (walk-in cash sale, one or
two items) to as few taps/clicks as possible.

1. **Cart building**: searchable product picker (active products from
   `list_active_products`), quantity input, "add to cart", repeatable for
   multiple lines. Running total updates live.
2. **Manual price override** — per `AGENTS.md` §7 / `DESIGN.md` §3.3: each
   cart line gets a small, secondary control (icon button or context menu,
   not a visible price field by default) to override that line's unit
   price. Overriding sets `price_manually_overridden = true` on that line
   when the sale is created. Do not make the price field editable by
   default — this is a deliberate friction point, not an oversight.
3. **Payment**: cash/QR amount fields that must sum to the cart total —
   validate client-side for immediate feedback, but the authoritative check
   remains `domain/validation.py`'s `validate_sale_payments` (invoked
   inside `create_sale`). Surface its error inline, in Spanish (from
   `strings_es.py`), rather than letting a raw exception surface.
4. **Credit ("fiado") toggle**: when on, hide the payment fields entirely
   and require `customer_name` (free text, no content validation per
   `DESIGN.md` §3.4); `customer_note` optional. Submitting calls
   `create_sale` with `is_credit=True` and no payments.
5. **Submit** calls
   `repositories/sales.create_sale(conn, items, payments, is_credit,
   customer_name, customer_note, user=session.current_user)`, then clears
   the cart and calls `on_change()`.
6. **Recent sales list** (e.g. today's sales) below or beside the entry
   form: time, items summary, total, payment method(s)/credit flag. Each
   row has:
   - **Void** — calls `void_sale`, behind a confirmation dialog (the data
     stays recoverable in history, but the UI shouldn't allow voiding by
     mis-click).
   - **Edit** — reopens the cart pre-filled with that sale's current
     items/payments; submitting calls `edit_sale` instead of `create_sale`.
     Reuse the same cart-building UI from steps 1–4, do not build a second
     form.
   - Do **not** expose full version history in this screen — this list only
     needs current-state + edit/void. A "ver historial" detail view is a
     future enhancement, not part of this plan.

**Exit criteria**: manually creating a cash sale, a split cash/QR sale, a
credit sale, editing a sale, and voiding a sale all work end-to-end against
a real (dev) SQLite file, and the balance banner reflects each change
immediately. Controller-level unit tests (no Flet) cover payment-sum
validation wiring and the override flag being set correctly.

---

## Task 3 — Catalog screen (`ui/views/catalog.py`)

1. List active products (name, current price) from `list_active_products`.
2. **Create product**: name + initial price → `create_product`.
3. **Edit price**: small form (new price, optional reason) →
   `update_product_price`. Show the previous price next to the new-price
   input for context; never let the previous value be edited directly.
4. **Deactivate/reactivate**: use whatever mechanism Task 0 confirmed was
   actually implemented for `set_product_active`. Deactivated products are
   **excluded** from the sales-screen product picker (Task 2) — that's the
   point of deactivating them — but remain visible here under a "mostrar
   inactivos" toggle so they can be reactivated later.

**Exit criteria**: creating a product, changing its price twice (confirm
both prior rows remain in `product_prices` history, unedited), and
deactivating/reactivating all work; the sales screen picker correctly
excludes inactive products.

---

## Task 4 — Restocking ("reponer stock")

`DESIGN.md`'s `ui/views/` list (§6) does not name a dedicated batches
screen — batches are logistical and tied to an expense (§3.2). This plan
makes an explicit scope call, flagged here for review rather than silently
decided: **restocking gets its own screen, `ui/views/restock.py`**,
reachable from the nav rail, rather than being buried as a dialog inside
Catálogo or Gastos — because it writes to three tables at once (expense,
batch, stock movements) and deserves a clear form of its own, not a modal
bolted onto an unrelated screen.

1. Multi-line form: pick product + quantity, repeatable (same interaction
   pattern as the sales cart, but with no pricing — batch items carry no
   cost per line, per `DESIGN.md` §3.2).
2. Single expense amount + description field for the whole batch (the total
   cost of the restock trip/order) — this becomes the linked `expenses`
   row.
3. Submit calls
   `repositories/batches.create_batch(conn, items, expense_amount,
   expense_description, user=session.current_user)`. Success clears the
   form and calls `on_change()` (the expense affects available balance).
4. Recent batches list: timestamp, item summary, linked expense
   amount/description — resolved via `resolve_batch_expense`; never
   re-derive the expense link by hand in the view.

**Exit criteria**: creating a batch inserts exactly one expense
(version 1), one batch row, N batch_items, and N positive stock_movements,
in a single transaction. If Plan #1's tests didn't already assert this
end-to-end through the repository, add that assertion now; the UI itself
only needs manual verification plus controller-level tests for form
validation.

---

## Task 5 — Expenses screen (`ui/views/expenses.py`)

1. List expenses (current version only, most recent first): description,
   amount, timestamp, user, and a **"vinculado a reposición" badge** when
   the expense is linked from a batch.
   - This requires a reverse lookup (given an expense `logical_id`, is
     there a batch referencing it?) that doesn't exist yet in the
     repository layer. Add it now as a small addition to
     `repositories/batches.py` — e.g.
     `find_batch_for_expense(conn, expense_logical_id)` — rather than
     joining ad hoc in the view. The Excel export in Plan #3 needs the same
     lookup for its "linked to restock" column (`DESIGN.md` §4.1), so build
     it once, correctly, here.
2. **Create expense** (plain, not linked to a batch): description + amount
   → `create_expense`.
3. **Edit / Void**: same pattern as sales — edit reopens a form pre-filled
   with the current version, void requires a confirmation dialog. If an
   expense is linked to a batch, voiding it does **not** cascade to void
   the batch or its stock movements (batches and expenses are separate
   entities joined by reference, not by lifecycle — do not add cascade
   logic that isn't in `DESIGN.md`); show a warning in the confirmation
   dialog that stock records will be unaffected, so the user isn't
   surprised later.

**Exit criteria**: creating, editing, and voiding a plain expense works; a
batch-linked expense correctly shows its badge and the warning-on-void
copy; controller tests cover the badge logic.

---

## Task 6 — Debts ("fiado") screen (`ui/views/debts.py`)

1. List open debts from `list_open_debts`: customer name, note, sale total,
   amount paid so far, outstanding balance.
2. **Mark as paid** — single button per row, no confirmation dialog, no
   extra fields (`AGENTS.md` §7: must stay one click). Calls
   `mark_debt_paid`.
3. **Abono (partial payment)** — secondary action (e.g. an expandable row
   or a small "abono parcial" link next to the main button) revealing an
   amount field, client-validated against the outstanding balance for
   immediate feedback, with the authoritative check still in
   `domain/validation.py`'s `validate_partial_payment`. Calls
   `record_partial_payment`.
4. A "mostrar saldadas" toggle to also see recently settled debts
   (read-only), so the owner can look up a customer's payment history
   without leaving the screen. Keep this minimal — no separate customer
   view (`DESIGN.md` §7: no customer database).

**Exit criteria**: marking a debt fully paid in one click, and recording a
partial payment that leaves the debt open with a reduced balance, both
work; attempting an abono larger than the outstanding balance is rejected
with a clear Spanish message.

---

## Task 7 — Cash count ("arqueo") screen (`ui/views/cash_counts.py`)

1. A single input for `counted_cash` plus an optional note.
2. On submit: compute `expected_cash` via
   `domain/balance.compute_expected_cash`, call `record_cash_count`, then
   immediately display the resulting difference clearly (e.g. "sobran $X" /
   "faltan $X" / "cuadra" — exact wording in `strings_es.py`) — this is the
   whole point of the screen, don't bury it in a list.
3. Below the entry form, a read-only history list of past counts
   (timestamp, user, counted, expected, difference, note) — no edit/delete
   affordance at all, since `DESIGN.md` §3.7 is explicit that a cash count
   is a snapshot, never retroactively corrected. Do not add a "corregir"
   action, even as a stretch goal.

**Exit criteria**: recording a cash count that matches, one that's short,
and one that's over all display the correct difference and sign; the
history list never offers to edit a past entry.

---

## Task 8 — View-layer testing strategy

Flet widget trees are harder to exercise under `pytest` than plain
functions, so keep the split from Task 1 strict:

1. **Controller modules** (`ui/views/<name>_controller.py`, no Flet
   imports): unit test these thoroughly — payment-sum checks, badge logic,
   button-enabled logic, Spanish message selection. These run in the
   normal `pytest` suite, no Flet involved.
2. **View modules** (`ui/views/<name>.py`): add one smoke test per view
   that builds its root control against a freshly migrated
   in-memory/temp SQLite connection and a fake `session`, asserting it
   doesn't raise. If a view's callbacks reference `page` directly (e.g.
   `page.update()`), guard those calls so `build()` doesn't require a live
   `Page` to construct — pass `page` in only where truly needed, and prefer
   calling `on_change()` over reaching for `page` directly. If the
   installed Flet version ships its own testing utilities that fit better
   than a hand-rolled fake session, use those instead of reinventing one.
3. No structural change needed to the CI workflow from Plan #1 Task 5 —
   `uv run pytest` already picks up these new tests once they exist under
   `tests/`.

**Exit criteria**: `uv run pytest` includes and passes controller unit
tests for all screens plus one build-smoke-test per screen.

---

## Task 9 — Manual QA pass

Automated coverage stops short of real interaction (clicking, typing) in
this plan, so add a short `MANUAL_QA.md` at the repo root: one checklist per
screen (the "Exit criteria" bullets above, phrased as steps), to be walked
through by hand against a built `uv run flet run` before considering this
plan's PR ready for review. This is a living document — Plan #3
(export/backup/archive/packaging) should append to it rather than replace
it.

**Exit criteria**: `MANUAL_QA.md` exists, covers all six screens (nav shell
+ five entity screens), and has been walked through at least once with
results noted in the PR description.

---

## Definition of done for this plan

- [ ] Task 0–9 exit criteria all met.
- [ ] `AGENTS.md` §10 checklist passes for every commit made under this
      plan.
- [ ] User indicator bar and balance banner are mounted once at the shell
      level and appear correctly on every screen.
- [ ] Manual price override on sale lines remains a secondary/hidden
      control, not a default-visible field.
- [ ] "Mark debt as paid" remains a single click with no confirmation
      dialog; "abono" remains available but requires one extra step.
- [ ] Cash counts have no edit/delete affordance anywhere in the UI.
- [ ] No new `UPDATE`/`DELETE` on business tables introduced by any view or
      controller — all writes go through Plan #1's repository functions.
- [ ] No product cost/margin/profit field or shift/schedule concept
      introduced anywhere in these screens (`AGENTS.md` §7, `DESIGN.md` §7).
- [ ] All UI-facing strings added in this plan live in `ui/strings_es.py`,
      none inline.

## Out of scope for this plan (Plan #3 and beyond)

- `services/excel_export.py` and its export screen (`DESIGN.md` §4) — note
  that Task 5's new `find_batch_for_expense` lookup is meant to be reused
  there, not duplicated.
- `services/backup.py` (on-demand file-copy backup) and any UI trigger for
  it.
- The "Archive and start a new ledger" action (`DESIGN.md` §3.9).
- `flet build windows` packaging and the QEMU verification step
  (`DESIGN.md` §5).
- A full version-history detail view for sales/expenses (this plan's list
  screens only show current state + edit/void).
- Any responsive/window-resizing polish beyond "usable" (`DESIGN.md` §1).
