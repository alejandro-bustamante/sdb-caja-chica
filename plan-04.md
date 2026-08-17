# Implementation Plan #4 — Archived Ledger Viewer (Read-Only)

## Status of this document

This is the **fourth** implementation plan for the Small Shop Sales Ledger
project. It builds on Plan #1 ("Foundations, Schema, and Core
Repositories"), Plan #2 ("Daily-Use UI Screens"), and Plan #3 ("Export,
Backup, Archiving, and Packaging"), all assumed complete: the six daily
screens work end to end, `domain/balance.py` correctly accounts for
`expense_payments` by method, Excel export and on-demand backup exist, and
"Archive and start a new ledger" (`DESIGN.md` §3.9) is implemented and
never mutates the file being archived.

`DESIGN.md` §3.9 names a possible future feature explicitly: *"a future
read-only 'open archived ledger' feature if it becomes useful."* Plan #3
listed it under "Out of scope (future)" without committing to it. This plan
is that commitment: it implements the archived-ledger viewer. Every other
item Plan #3 left out of scope stays out of scope here too — see the
"Explicitly still out of scope" section at the end, which distinguishes
things that were merely *deferred* from things that are *permanent
non-goals* and should not be revisited without a design change to
`DESIGN.md` itself.

This plan does **not** re-litigate `DESIGN.md` or `AGENTS.md`. Where an
earlier plan left an open decision for review, assume it was already
settled — read the existing code, don't re-decide it here.

**Scope of this plan**: let the user open any old, archived `.db` file
(one created by a previous "Archive and start a new ledger" action, or any
ledger file the user has stored outside the app's default folder) inside
the running app, browse it with the same six screens already built, and
export from it — all strictly read-only, and all without touching the
currently active ledger file or requiring an app restart.

**Audience**: same as the previous plans — an LLM coding agent with direct
repository access, working autonomously or semi-autonomously through the
tasks below. Read `DESIGN.md`, `AGENTS.md`, `plan-01.md`, `plan-02.md`, and
`plan-03.md` in full before starting Task 0.

**Language convention reminder (do not violate)**: all code, identifiers,
comments, and this plan are in English. Every string the shop user reads is
Spanish and lives only in `ui/strings_es.py`. See `AGENTS.md` §3.

---

## Task 0 — Recap and verification before starting

1. Confirm Plan #3's exit criteria still hold on the current branch:
   `uv run pytest` passes, `uv run flet run` boots to the full shell, the
   balance banner correctly splits cash/QR expenses, export/backup/archive
   all work.
2. Re-read the **current, real** implementation of the following — this
   plan depends on all three more than any previous plan did, so do not
   assume signatures from the plan text:
   - Wherever the live `conn`/session state actually lives (Plan #2, Task
     0 and Plan #3, Task 5.2 both asked this same question — reuse that
     exact answer a third time; if it turned out to need a refactor in
     Plan #3, this plan builds on the refactored version).
   - The exact shape of the "Archive and start a new ledger" menu action
     (Plan #3, Task 5) — this plan's new menu action sits next to it and
     must not be confusable with it in the UI.
   - `db/connection.py`'s migration runner (Plan #1, Task 1) — this plan
     reuses it as-is against a temporary copy (see Task 1 below); confirm
     it is safely re-runnable against an arbitrary file path, not hardcoded
     to the app's default DB location.
3. Record in the tracking PR/commit which of the above were confirmed
   against real code.

**Exit criteria**: a short note (first commit message, or a comment at the
top of the tracking PR) confirming the audit above was performed against
the real code.

---

## Task 1 — Decide and implement how an old-schema archived file gets read

An archived file was written by whatever app version was current when it
was archived. By the time someone opens it again, the running app may be
several migrations ahead. This is the first real design decision this plan
must make, and it's made explicit here rather than silently picked, the
same way Plan #1 flagged `products.active` and Plan #3 flagged the
debt-payment method:

- **(a) Strict read-only, no migration.** Open the file exactly as it is,
  refuse to open it if `schema_version` doesn't match the current app's
  latest migration, and show a clear Spanish error telling the user the
  file is from an older (or newer) app version.
- **(b) Migrate a throwaway copy.** Copy the archived file to a temp path,
  run the existing migration runner (Plan #1, Task 1) against the *copy*,
  and open the copy read-only for viewing. The original file on disk is
  never touched — copying it before migrating is what guarantees that.
  Delete the temp copy when the viewer is closed.

**Default to (b)** if no reviewer input is available before this task
needs to ship, since it lets someone open a ledger archived years ago
without forcing them to keep an old app version around, and it reuses
machinery that already exists (Task 1's migration runner, already proven
byte-for-byte-safe by Plan #3's archive feature). Leave a
`# TODO(reviewer): confirm archived-file migration strategy` comment at the
relevant line if taking this default. Flag the decision explicitly in the
PR description either way.

If (b) is taken:

1. Add `db/connection.py::prepare_archived_copy(source_path, tmp_dir) ->
   copy_path`: copies the file (and, if present, any `-wal`/`-shm`
   sidecars — checkpoint them into the copy first via
   `PRAGMA wal_checkpoint(TRUNCATE)` on a throwaway connection to the
   *copy*, never the original, mirroring the backup logic from Plan #3,
   Task 4), then runs the migration runner against the copy.
2. If the copy's `schema_version` is *ahead* of what this app version
   knows how to read (i.e. the archived file came from a newer app
   version than the one currently running), fail with a clear Spanish
   error rather than guessing — do not attempt to "downgrade" a schema.
3. Add `db/connection.py::open_readonly_connection(path) -> conn`: opens
   the given path with the SQLite URI read-only mode
   (`file:{path}?mode=ro`) and additionally sets `PRAGMA query_only = ON`
   as a second, belt-and-suspenders guard (see Task 2) — the URI mode
   alone protects the file on disk, `query_only` protects against any
   in-app code path that forgets which connection it's holding.

**Exit criteria**: a test that takes a small pre-migrated fixture `.db`
file frozen at an older migration number, runs `prepare_archived_copy`
against it, and asserts: the original fixture file is byte-for-byte
unchanged afterward, the copy's `schema_version` matches the current
latest migration, and all pre-existing data in the copy is intact and
readable through the existing repository read functions.

---

## Task 2 — Guard against accidental writes to a read-only connection

Every repository write function already funnels through the transaction
helper from Plan #1, Task 1 (`AGENTS.md` §4). This task adds one guard
there rather than touching every individual repository function:

1. In the transaction helper (`with transaction(conn) as cur: ...`), check
   `PRAGMA query_only` on the connection before beginning; if it's `ON`,
   raise a clear, typed exception (e.g. `ReadOnlyLedgerError`) immediately,
   before any SQL runs — never let a write silently no-op against a
   read-only connection.
2. This is a single change in one shared place, consistent with how
   `AGENTS.md` §4 already centralizes transaction handling — do not
   duplicate the check into each repository module.

**Exit criteria**: a test that opens a connection via
`open_readonly_connection` and calls any existing write repository
function (e.g. `create_expense`) against it, asserting
`ReadOnlyLedgerError` is raised and no row was inserted.

---

## Task 3 — Read-only mode for the existing view/controller contract

Plan #2, Task 1 established the `build(conn, session, on_change) ->
ft.Control` contract for every screen. This plan extends it rather than
building parallel read-only screens:

1. Add a `read_only: bool` field to whatever session/shared-state object
   already carries `conn` and `current_user` (Task 0 confirmed where that
   lives). Default `False` for the normal live-ledger flow — no behavior
   change there.
2. In each `ui/views/<name>.py` and its `_controller.py` (sales, catalog,
   restock, expenses, debts, cash_counts): read `session.read_only` and,
   when true, hide or disable every control that would write — "add to
   cart"/submit, edit, void, mark-as-paid, abono, create product,
   deactivate/reactivate, record cash count, create batch. Lists, current
   balances, and history stay fully visible and functional; only the
   write affordances disappear.
3. Prefer disabling this once per screen at the top of `build()` (e.g.
   skip mounting the write-related controls entirely when `read_only` is
   true) over sprinkling `if session.read_only` checks through every
   button handler — the former is easier to audit for completeness against
   `AGENTS.md` §10's checklist.
4. The persistent user indicator bar (`AGENTS.md` §7) does not apply the
   same way while browsing an archived file — nobody is "acting" in it.
   Replace it, only while `read_only` is true, with a distinct, equally
   hard-to-miss banner: filename of the archived ledger plus a clear
   "SOLO LECTURA" label (exact copy in `strings_es.py`). Do not remove the
   balance banner — the archived ledger's own historical balance is still
   useful to see, it just describes a past ledger, not the live one.

**Exit criteria**: with `session.read_only = True` and a fake read-only
`conn`, a build-smoke-test per screen (same pattern as Plan #2, Task 8)
confirms it constructs without raising and that no write-triggering
control is present in the resulting control tree. A manual pass confirms
every list still renders real data from a sample archived file.

---

## Task 4 — "Abrir ledger archivado" menu action

1. Add a new menu action, distinct from and listed separately from
   "Archivar y empezar nuevo ledger" (Plan #3, Task 5) — different label,
   different icon, grouped together in the menu since they're related but
   never worded similarly enough to be confused in a glance. Spanish copy
   in `strings_es.py` (e.g. "Abrir ledger archivado…").
2. Uses Flet's file picker to let the user choose any `.db` file (not
   restricted to the app's own `Documents/<AppName>/` folder — the whole
   point is being able to open a file that was moved or backed up
   elsewhere).
3. On selection: call `prepare_archived_copy` then `open_readonly_connection`
   (Task 1), set `session.read_only = True` with the new connection and a
   display name (original filename), and switch the shell's content area
   into archive mode — reusing the exact same nav rail and six screens
   (Task 3), not a second parallel UI.
4. Add a "Cerrar ledger archivado" action, shown only while in archive
   mode, that restores the shell to the normal live-ledger session
   (original `conn`, `read_only = False`) and deletes the temporary copy
   created in Task 1.
5. While in archive mode, hide "Abrir ledger archivado" and "Archivar y
   empezar nuevo ledger" both — opening a nested archive, or archiving an
   already-read-only view, are not meaningful actions. Flag this exclusion
   explicitly in the PR description as a deliberate scope decision, not an
   oversight.

**Exit criteria**: opening a real archived file (produced by Plan #3's
archive action) shows correct historical data across all six screens with
every write control absent; the original archived file and the currently
active live ledger file are both byte-for-byte unchanged after the whole
open → browse → close cycle; closing returns the app to normal live-ledger
operation without a restart.

---

## Task 5 — Excel export from an archived ledger

`services/excel_export.py::export_range` (Plan #3, Task 3) already takes
an open `conn` and does not care whether it's the live connection or not.

1. Reuse the existing export screen (`ui/views/export.py`) unchanged in
   archive mode — it already goes through `session`/`conn`, so no new code
   should be needed here beyond making sure it's included in the archive
   mode's nav rail (Task 3/4) and that it doesn't attempt any write.
2. If the export screen currently assumes it can always write a backup or
   touch the live ledger path in any way, fix that assumption here — it
   must work purely off whatever `conn` it's given.

**Exit criteria**: exporting a date range from an opened archived ledger
produces a workbook whose figures match that archived ledger's own
historical balance, independent of and unaffected by the currently active
live ledger.

---

## Task 6 — Testing for this plan's new surfaces

1. Repository/connection tests for Task 1 (byte-for-byte original file
   preservation, schema-mismatch handling) and Task 2 (write guard).
2. Controller tests for Task 3's `read_only` branching, covering at least
   one representative screen per write-affordance type (a create action,
   an edit action, a one-click action like "mark as paid").
3. One integration test that runs the full open → browse → export → close
   cycle against a fixture archived file and asserts the live ledger's own
   data and balance are completely unaffected throughout.

**Exit criteria**: `uv run pytest` passes with all of the above included.

---

## Task 7 — Manual QA pass

Append a new section to the existing `MANUAL_QA.md` (started in Plan #2,
Task 9; extended in Plan #3, Task 8) covering: opening an archived file,
confirming every screen shows historical data with no write controls
visible, confirming the "SOLO LECTURA" banner is unmissable, exporting
from the archived view, and closing it to confirm the live ledger is
exactly as it was before.

**Exit criteria**: `MANUAL_QA.md` includes this section, walked through at
least once with results noted in the PR description.

---

## Definition of done for this plan

- [ ] Task 0–7 exit criteria all met.
- [ ] `AGENTS.md` §10 checklist passes for every commit made under this
      plan.
- [ ] The archived-file migration strategy decision (Task 1) is explicitly
      recorded as decided in the PR description, not silently defaulted
      without a note.
- [ ] No write repository function can execute against a read-only
      connection without raising `ReadOnlyLedgerError` first.
- [ ] Opening, browsing, exporting from, and closing an archived ledger
      never mutates the archived file or the currently active live ledger
      file, verified byte-for-byte in at least one automated test.
- [ ] Every write-triggering control (create/edit/void/mark-paid/abono/
      record cash count) is absent, not merely disabled-but-present, in
      every screen while `session.read_only` is true.
- [ ] "Abrir ledger archivado" and "Archivar y empezar nuevo ledger" are
      visually and textually distinct in the menu.
- [ ] All new UI-facing strings live in `ui/strings_es.py`, none inline.

## Explicitly still out of scope

Distinguishing what this plan intentionally does not touch, and why:

**Deferred, could be picked up in a future plan if ever needed:**
- Editing which folder/recent-files list the "Abrir ledger archivado"
  picker remembers, or any "recent archived ledgers" shortcut — the plain
  file picker is enough for the expected low frequency of use.
- Any indication in the live ledger of which files have previously been
  archived — `DESIGN.md` doesn't track this and this plan doesn't add it.

**Permanent non-goals — do not revisit without a `DESIGN.md` change:**
- Any UI to reconcile, correct, or annotate a historical `cash_counts`
  discrepancy, whether viewed live or archived — `DESIGN.md` §3.7 is
  explicit that a cash count is a snapshot and there is never a
  "corregir" action. This plan's read-only viewer makes this doubly true
  for archived data: it is not just undesirable but structurally
  impossible, since the connection is read-only.
- Any write path into an archived file, including "importing" data back
  from an archive into the live ledger, or merging two ledger files —
  `DESIGN.md` §3.9 describes archiving as one-directional and this plan
  does not add a reverse path.
- Full UI automation testing beyond the smoke tests and manual QA
  checklist established across all four plans.
- Any packaging target other than Windows (`DESIGN.md` §5).
