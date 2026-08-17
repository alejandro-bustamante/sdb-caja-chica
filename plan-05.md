# Implementation Plan #5 — Audit Trail Screen and Windows CI Build

## Status of this document

This is the **fifth** implementation plan for the Small Shop Sales Ledger
project. It builds on Plans #1–#4, all assumed complete: full repository/
domain layer, the six daily screens, Excel export, backup, "archive and
start a new ledger," and the read-only archived-ledger viewer.

This plan closes two gaps identified by reviewing all prior plans against
what's actually implemented:

1. **Audit trail UI.** `plan-02.md` explicitly deferred this twice — Task
   2.6 ("Do not expose full version history in this screen... a 'ver
   historial' detail view is a future enhancement, not part of this plan")
   and Task 5 (same note for expenses). No later plan picked it back up.
   The data has been fully auditable at the database level since Plan #1
   (that's the entire point of the append-only design in `DESIGN.md` §2),
   but nothing in the UI surfaces it — a user who wants to know "who
   changed what, and when" today has no option but to open the `.db` file
   directly and reconstruct it from `logical_id`/`version`/
   `superseded_at`/`deleted_at` by hand, which defeats the purpose.
2. **Windows CI build.** `plan-03.md` Task 6 scoped `flet build windows`
   plus a QEMU boot-verification step, extending the CI skeleton from
   `plan-01.md` Task 5. It was not carried out. This plan implements the
   build/artifact half of that task now, as a deliberately smaller task
   than originally scoped — see Task 6 below for what's included and what
   stays deferred.

This plan does **not** re-litigate `DESIGN.md` or `AGENTS.md`. Where an
earlier plan left an open decision for review, assume it was already
settled — read the existing code, don't re-decide it here.

**Audience**: same as the previous plans — an LLM coding agent with direct
repository access, working autonomously or semi-autonomously through the
tasks below. Read `DESIGN.md`, `AGENTS.md`, and `plan-01.md` through
`plan-04.md` in full before starting Task 0.

**Language convention reminder (do not violate)**: all code, identifiers,
comments, and this plan are in English. Every string the shop user reads is
Spanish and lives only in `ui/strings_es.py`. See `AGENTS.md` §3.

---

## Task 0 — Recap and verification before starting

1. Confirm Plan #4's exit criteria still hold on the current branch:
   `uv run pytest` passes, opening/browsing/closing an archived ledger
   works and never mutates either file involved.
2. Re-read the current, real implementation of:
   - The `build(conn, session, on_change) -> ft.Control` view contract and
     the `session.read_only` flag added in Plan #4, Task 3 — this plan's
     new screen must be constructed the same way and must work correctly
     whether `session.read_only` is `True` (browsing an archived ledger)
     or `False` (live ledger). Auditing is read-only by nature either way,
     but reusing the exact same session/shell plumbing means the audit
     screen "just works" for archived ledgers too, with no special-casing.
   - `db/repositories/batches.py::find_batch_for_expense` (Plan #2, Task
     5) and `resolve_batch_expense` (`AGENTS.md` §5a) — reused for audit
     summaries that mention restock linkage.
   - Whether `products.active` toggling ended up versioned or a plain
     mutable flag (flagged open in Plan #1, Task 2.2, assumed settled by
     now) — this determines whether product activation/deactivation can
     appear in the audit trail at all (see Task 1.3 below).
3. Record in the tracking PR/commit which of the above were confirmed
   against real code.

**Exit criteria**: a short note (first commit message, or a comment at the
top of the tracking PR) confirming the above was checked against the real
code.

---

## Task 1 — Normalized audit event query (`domain/audit.py`)

The audit screen must read from the existing tables directly — no new
tables, no denormalized "audit log" that could itself drift out of sync
with the real data (that would reintroduce exactly the failure mode
`DESIGN.md` §2 exists to prevent). This task is a **read-only query layer**
over what already exists.

### 1.1 Event categories and change types

Map every business table to the six categories already visible as nav
screens, so a user can always connect an audit entry back to "the screen
where I'd normally see this":

| Category (Spanish label) | Source table(s) |
|---|---|
| Ventas | `sales` |
| Catálogo | `product_prices` (+ `products` creation) |
| Reponer stock | `batches` / `batch_items` |
| Gastos | `expenses` |
| Fiado | `debt_payments` (on `sales` where `is_credit=1`) |
| Arqueo | `cash_counts` |

Map every event to exactly one of three change types, matching the filter
vocabulary requested:

- **Registro** — the first version of a versioned entity (`version = 1`,
  `deleted_at IS NULL`), or any row from a naturally single-event table
  (`debt_payments`, `cash_counts`, `batches`, first `product_prices` row
  for a product).
- **Edición** — any later version of a versioned entity
  (`version > 1`, `deleted_at IS NULL`), including a later `product_prices`
  row (a price change) and a reassigned sale (`current_user` changed).
- **Eliminación** — any version with `deleted_at` set (a voided sale or
  expense). Note there is no "eliminación" for products, batches,
  `debt_payments`, or `cash_counts`, since none of those support a void/
  delete operation anywhere in the app — the type filter simply returns no
  rows for those categories when "eliminación" is selected, which is
  correct behavior, not a gap to fill.

### 1.2 Query implementation

- `list_audit_events(conn, *, since=None, until=None, user_id=None,
  categories=None, change_types=None, limit=50, offset=0) ->
  list[AuditEvent]` — builds one `UNION ALL` SQL query across the six
  source table groups above, applying all filters in SQL (not filtering a
  fully-fetched Python list), ordered by timestamp descending, with
  `LIMIT`/`OFFSET` for pagination. `AuditEvent` carries: `category`,
  `change_type`, `entity_logical_id` (nullable for the non-versioned
  tables), `timestamp`, `user_id`, and enough of the underlying row's
  fields (amounts, product/customer names, old/new price, etc.) for Task 2
  to build a summary from — do not discard those fields just because the
  UI won't show every one by default.
- `count_audit_events(conn, **same filters) -> int` — for showing "N
  resultados" and driving the "cargar más" pagination in Task 3, using the
  same `WHERE` clauses as `list_audit_events` so the count and the list
  never disagree.
- Time filters accept the four presets requested (1 hour, 24 hours, 7
  days, 30 days) computed as `now - interval`, plus an explicit "todo" (no
  lower bound) option — do not silently cap "todo" without telling the
  user, since an audit tool that quietly hides old data defeats its
  purpose; instead, "todo" is allowed but paginated (see Task 3).

### 1.3 Known limitation — `products.active` is not audited

If Task 0 confirms `products.active` is a plain mutable flag (Plan #1,
Task 2.2's recommended default), then toggling it produces no row anywhere
that this task can query — it is a genuine `UPDATE`, not an append-only
event, by design (`AGENTS.md` §1 explicitly allows this one exception).
This means activating/deactivating a product will **not** appear in the
audit trail. Do not attempt to work around this by adding a parallel log
table just for this one field — that would be exactly the kind of
denormalized, driftable audit log this task is designed to avoid. Instead:

- Note the limitation in a comment in `domain/audit.py`.
- Leave a `# TODO(reviewer): products.active has no history; would need
  Plan #1's decision revisited to version it` for future consideration.
- This is the only gap of its kind; every other business fact already goes
  through the versioned/append-only pattern and is fully auditable.

**Exit criteria**: tests covering each of the six categories independently,
each of the three change types independently, combined filters, the "todo"
time option, and pagination (`limit`/`offset` correctness against
`count_audit_events`). One test confirms a deactivated-then-reactivated
product produces zero audit events, documenting the known limitation
rather than silently passing for the wrong reason.

---

## Task 2 — Human-readable summaries (`ui/views/audit_controller.py`)

No Flet imports here, per the controller pattern established in Plan #2,
Task 1.2 — this stays unit-testable on its own.

1. One summary-builder function per category, turning an `AuditEvent` (plus
   whatever underlying fields Task 1 attached to it) into a single Spanish
   sentence, e.g.:
   - Ventas, registro: *"Venta registrada por Ana — $45.00 (efectivo)"*
   - Catálogo, edición: *"Precio de 'Coca-Cola 600ml' editado por Juan:
     $15.00 → $18.00"*
   - Gastos, eliminación: *"Gasto 'Alquiler local' anulado por Ana"*
   - Fiado, registro: *"Abono de $20.00 recibido de 'María Pérez' por
     Juan"*
2. Keep summaries at the level of business facts a shop owner cares about
   — amounts, who, what — and never mention `logical_id`, `version`,
   `superseded_at`, or `deleted_at` by name anywhere in the UI text. Those
   are implementation details of how the append-only design works, not
   something the user needs to know about (per this plan's brief: *"la app
   no necesita dejar ver detalles de la implementación del softdelete"*).
3. Add all new Spanish text to `strings_es.py` as templates, not
   hand-built strings scattered through the controller.

**Exit criteria**: unit tests for at least one summary per (category,
change_type) combination that's actually reachable per Task 1.1's table
(e.g. no "Catálogo, eliminación" test, since that combination never
occurs).

---

## Task 3 — Auditoría screen (`ui/views/audit.py`)

1. Add "Auditoría" as a seventh entry in the nav rail (Plan #2, Task 1),
   positioned after the six daily screens — it is a cross-cutting tool,
   not a daily-entry screen, so it reads last in the list. Reachable from
   both a live ledger session and an archived-ledger session (Plan #4);
   no special-casing needed since it never writes.
2. Filter bar at the top of the screen:
   - **Tiempo**: segmented control or dropdown — "Última hora" / "Últimas
     24 horas" / "Últimos 7 días" / "Últimos 30 días" / "Todo". Default to
     "Últimas 24 horas" on first load, so the screen never opens by
     fetching the entire history of a long-running ledger.
   - **Usuario**: dropdown populated from `users` (active and inactive —
     an inactive user may still have made changes worth auditing), plus a
     "Todos" option.
   - **Categoría**: multi-select across the six categories from Task 1.1,
     plus "Todas" as a shortcut to select/clear all.
   - **Tipo de cambio**: multi-select across "Registro" / "Edición" /
     "Eliminación", plus "Todas".
   - Changing any filter re-queries via `list_audit_events` /
     `count_audit_events` (Task 1) and resets pagination to the first
     page.
3. Results list, newest first, one row per event: timestamp, category
   badge, change-type badge (visually distinct colors — e.g. registro
   neutral, edición amber, eliminación red — consistent with how void/edit
   actions are already styled elsewhere in the app), user, and the Task 2
   summary sentence. Show a result count ("N cambios encontrados") above
   the list, from `count_audit_events`.
4. Pagination: a page size in line with the other list screens (e.g. 50),
   with a "Cargar más" button appending the next page rather than a full
   numbered pager — simplest control that fits `DESIGN.md` §1's low-
   friction/simple-UI priority.
5. This screen has **no** create/edit/void/mark-paid controls of any kind
   — not hidden-when-read-only like Plan #4's `session.read_only` screens,
   but structurally absent, since auditing is never a write path in any
   session. Do not wire it through the `session.read_only` branching from
   Plan #4, Task 3; that mechanism exists for screens that have write
   controls to hide. This screen simply never has any.

**Exit criteria**: manually applying each filter individually and in
combination against a dev database with a mix of creates/edits/voids
across all six categories returns the expected events; pagination loads
correctly past the first page; the screen renders identically (aside from
the archived filename banner from Plan #4) whether opened against the live
ledger or an archived one. A build-smoke-test (Plan #2, Task 8 pattern)
confirms it constructs without raising in both session modes.

---

## Task 4 — Optional expandable detail for edits (recommended, not blocking)

For an edited or voided entity, a shop owner may want to see the specific
before/after values, not just "fue editado." This task reuses existing
read functions rather than adding new ones:

1. Add a "ver detalle" expand/collapse affordance on rows where
   `change_type` is "Edición" or "Eliminación".
2. On expand, call the existing history read helpers per category —
   `get_sale_history` (sales), the full `product_prices` row set for that
   product, the equivalent for `expenses` — and show a compact "antes →
   después" comparison of just the fields that actually changed, still in
   plain business language (e.g. "Cantidad: 2 → 3", never raw version
   numbers).
3. Keep this presentational only — no new repository writes, no new
   repository read functions beyond what Plan #1/#2 already built for the
   existing edit/history flows.

**Exit criteria**: expanding an edited sale or expense shows a correct,
readable before/after diff; this task's exit criteria are not required for
Task 3's own exit criteria to be considered met — if time-constrained,
ship Task 3 without this and note it as a fast-follow.

---

## Task 5 — Excel export tie-in

Two complementary pieces, per the brief's explicit ask for an Excel export
of the audit trail:

### 5.1 Add an "Auditoría" sheet to the general export

- Extend `services/excel_export.py::export_range` (Plan #3, Task 3) with a
  fifth sheet listing every audit event in the chosen date range, across
  all categories and change types — consistent with how the other four
  sheets are range-only with no additional filtering, so this sheet is a
  complete record for that period.
- Columns: category, change type, timestamp, user, summary (reuse Task 2's
  summary builders so the workbook text matches the on-screen text
  exactly).

### 5.2 Dedicated "Exportar esta vista" action on the Auditoría screen

- Add `services/excel_export.py::export_audit_events(conn, filters,
  output_path)` — a single-sheet workbook using the **exact filters
  currently active** in the Task 3 screen (time range, user, categories,
  change types), not the full unfiltered history. This is the more useful
  export for an actual audit ("show me everything Juan touched in the
  last 7 days" as a file to hand someone), distinct from 5.1's always-
  complete record.
- Wire a button on the Auditoría screen that calls this with the current
  filter state and Flet's file picker, mirroring the existing export
  screen's success/error messaging pattern (Plan #3, Task 3.2).

**Exit criteria**: the general export's Auditoría sheet matches what
Task 3's screen would show with "Todo/Todos/Todas" filters for the same
date range; the dedicated export button produces a workbook that exactly
matches the currently filtered on-screen results, including when filters
narrow it to a single user/category/type.

---

## Task 6 — Windows build via GitHub Actions (minor scope, as requested)

This is deliberately smaller than the original `plan-03.md` Task 6, which
bundled the build step together with a QEMU boot-verification VM. Per this
plan's brief, only the build/artifact half ships now:

1. Extend the existing CI workflow (`plan-01.md` Task 5) with a
   `flet build windows` step producing the `.exe`.
2. Upload the built output as a workflow artifact (e.g. via
   `actions/upload-artifact`) so it's downloadable from the Actions run
   without needing a tag or release step first.
3. Gate the build step so it doesn't run on every single push if that's
   too slow/costly for normal iteration — a reasonable default is: run
   tests (already existing) on every push/PR, but only run the
   `flet build windows` step on pushes to the main branch or on version
   tags. Document whichever trigger is chosen in the workflow file's
   comments and in `README.md`, so it's not ambiguous later.
4. Document in `README.md` how to fetch and run the CI-built `.exe`
   locally for a manual smoke check.

**Explicitly deferred, not part of this task**: the QEMU boot-verification
step from `plan-03.md` Task 6 remains unimplemented. Flag this in the PR
description as still-open scope, not silently dropped — it can be picked
up as a small follow-up once there's a concrete need for it (e.g. before a
first real release to the shop owner), rather than being bundled into this
already-broad plan.

**Exit criteria**: a commit to the main branch (or a tag, per whichever
trigger was chosen) produces a downloadable Windows `.exe` artifact from
the GitHub Actions run; `README.md` documents how to get it.

---

## Task 7 — Testing for this plan's new surfaces

1. `domain/audit.py` query tests — see Task 1's exit criteria; these are
   the most important tests in this plan, since an audit tool that
   silently drops or misattributes events is worse than no audit tool.
2. Controller tests for Task 2's summary builders, one per reachable
   (category, change_type) pair.
3. `services/excel_export.py` tests for both the new sheet (5.1) and the
   filtered export (5.2), confirming figures match `domain/audit.py`
   output for the same filters.
4. One view-level smoke test for `audit.py`, in both a live session and a
   read-only/archived session (Plan #4 pattern).

**Exit criteria**: `uv run pytest` passes with all of the above included.

---

## Task 8 — Manual QA pass

Append a new section to `MANUAL_QA.md` covering: applying each filter
individually and combined on the Auditoría screen, expanding a detail row
(Task 4, if shipped), both Excel export paths (Task 5.1 and 5.2), and
downloading/running the CI-built Windows artifact (Task 6) as a manual
smoke check in place of the deferred QEMU step.

**Exit criteria**: `MANUAL_QA.md` includes this section, walked through at
least once with results noted in the PR description.

---

## Definition of done for this plan

- [ ] Task 0–8 exit criteria all met (Task 4 may be deferred per its own
      note without blocking the rest).
- [ ] `AGENTS.md` §10 checklist passes for every commit made under this
      plan.
- [ ] The Auditoría screen is strictly read-only: no create/edit/void/
      mark-paid control exists anywhere on it, in either session mode.
- [ ] No UI text anywhere in the audit trail mentions `logical_id`,
      `version`, `superseded_at`, or `deleted_at` — summaries stay at the
      level of business facts.
- [ ] The `products.active` audit limitation (Task 1.3) is noted in code
      and, if a reviewer decides it matters enough, flagged for a future
      plan rather than worked around with a parallel log table.
- [ ] Both audit export paths (general sheet and filtered dedicated
      export) produce figures that match what `domain/audit.py` returns
      for the same filters.
- [ ] CI produces a downloadable Windows `.exe` artifact; the deferred
      QEMU verification is explicitly noted as still-open in the PR, not
      silently dropped.
- [ ] All new UI-facing strings live in `ui/strings_es.py`, none inline.

## Out of scope for this plan (future)

- The QEMU boot-verification step from `plan-03.md` Task 6 — deferred, not
  cancelled (see Task 6 above).
- Versioning `products.active` to make it auditable — would revisit Plan
  #1's original decision; flagged but not undertaken here.
- Full field-by-field diffing for every entity type in Task 4's detail
  view — only the fields most relevant to each category are shown.
- Any audit-log write path, alerting, or notification system (e.g.
  "notify me when someone voids a sale") — this plan is a passive viewer,
  not a monitoring system; `DESIGN.md` scopes this app for a 2–3-person
  shop where that kind of infrastructure isn't warranted.
