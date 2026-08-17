# Manual QA Checklist — Plan #2 (Daily-Use UI Screens)

Walk through every checklist below by hand against a running app
(`uv run flet run`) before considering the Plan #2 PR ready for review. Note
the results (passed / issue observed + steps to reproduce) in the PR
description.

Plan #3 (Excel export, backup, archive-and-new-ledger, packaging), Plan #4
(archived-ledger viewer) and Plan #5 (audit trail screen + Windows CI build)
append their own checklists here rather than replace this file.

Setup for the pass: start with a fresh dev ledger (`SDB_CAJA_CHICA_DATA_DIR`
pointing at an empty temp folder, or clear `dev-data/ledger.db`).

---

## Nav shell

- [x] App boots to the user picker ("¿Quién está trabajando ahora?").
- [x] Selecting a user takes you to a shell with the six destinations visible:
      Ventas, Catálogo, Reponer stock, Gastos, Fiado, Arqueo.
- [x] The current-user indicator bar and the "Disponible total" banner are
      visible on **every** screen (switch between all six and confirm).
- [x] Balance banner shows total, efectivo and QR.
- [x] $1 sale → balance banner increases by $1 **immediately** after saving
      from the Ventas screen.

## Ventas

- [x] Cash sale, one item: pick product, qty 1, add, enter exact cash payment,
      submit. Sale appears in "Ventas de hoy"; stock/banner reflect it.
- [x] Split cash/QR sale: total must equal cash+QR; when it doesn't, a Spanish
      hint shows the shortfall; submitting with a mismatch is blocked.
- [x] Credit sale: enable "Venta a crédito (fiado)", payment fields hide,
      customer name is required; submit with no payments works, stock decreases,
      no money added to balance banner.
- [x] Manual price override: click the price icon on a cart line, set a
      different price, confirm. The line shows the override badge; the saved
      sale carries `price_manually_overridden = true` (verify in DB).
- [x] Multiple lines: adding the same product twice merges its quantities.
- [x] Edit a today sale: click the edit icon, confirm the cart is pre-filled
      (items + payments/prices), change something, submit. A new version is
      created (check `sales` history for two rows, `superseded_at` set on the
      first). Stock and balance reflect the edited sale.
- [x] Void a today sale: click the undo icon, confirm in the dialog. Balance
      and stock return, sale disappears from the list.
- [x] Editing/voiding a credit sale that already has debt collections is
      rejected with a Spanish message.

## Catálogo

- [x] Create a product (name + price) — appears in the list and in the Ventas
      picker.
- [x] Change a product's price twice; each change shows the previous price in
      the dialog. In DB, `product_prices` holds all three rows untouched, only
      the first two superseded.
- [x] Deactivate a product — it disappears from the Ventas product picker but
      stays in Catálogo under its inactive badge.
- [x] "Mostrar inactivos" toggle shows inactive products; reactivating one puts
      it back in the Ventas picker.
- [x] Empty/invalid price and empty name are rejected with Spanish messages.

## Reponer stock

- [x] Multi-line batch: add two products with quantities, plus an expense
      amount and description, submit. Verify in DB: exactly one expense row
      (version 1), one batch, two `batch_items`, two positive
      `stock_movements`, in a single transaction.
- [x] Batch with no expense amount is allowed ("Sin gasto vinculado").
- [x] Stock for each product increases; balance banner drops by the expense
      amount.
- [x] Recent list shows timestamp, item summary, and the linked expense
      amount/description resolved through the link (not hand-decoded).

## Gastos

- [x] Create a plain expense (description + amount) — appears in the list and
      reduces the balance banner.
- [x] Edit an expense — form reopens pre-filled, save creates a new version
      (verify two `expenses` rows for the logical_id).
- [x] Void an expense — confirmation dialog; the expense stops counting against
      balance; a soft-deleted row remains.
- [x] An expense created via Reponer stock shows the "Vinculado a reposición"
      badge.
- [x] Voiding a batch-linked expense shows the warning that stock records will
      be unaffected; after voiding, `stock_movements` are indeed untouched.

## Fiado

- [x] Open debt rows show customer, note, total, paid, outstanding.
- [x] "Marcar pagado" settles an open debt in one click (no dialog, no extra
      field). Done.
- [x] Abono: expand "Abono parcial", enter an amount, submit — debt stays open
      with a reduced outstanding; balance increases by the abono.
- [x] An abono larger than the outstanding balance is rejected with a clear
      Spanish message.
- [x] "Mostrar saldadas" reveals settled debts (read-only).

## Arqueo

- [x] Recording an exact count shows "La caja cuadra".
- [x] Recording less than expected shows "Faltan $ X".
- [x] Recording more than expected shows "Sobran $ X".
- [x] Each result is shown prominently right after submitting.
- [x] History list shows timestamp, user, counted, expected, difference, note —
      and offers no edit/delete affordance for past entries.

---

# Manual QA Checklist — Plan #4 (Archived Ledger Viewer, Read-Only)

Walk through this checklist by hand against a running app (`uv run flet run`)
before considering the Plan #4 PR ready for review. Note the results
(passed / issue observed + steps to reproduce) in the PR description.

Setup: start from a normal live ledger with some data in all six screens
(sales, catalog, restock, expenses, debts, cash counts). Then use
"Archivar y empezar un nuevo libro" once so a real archived `.db` file exists
in the data folder (it stays untouched), and keep working in the new live
ledger for a bit so the two ledgers visibly differ.

## Abrir ledger archivado

- [ ] The menu shows three distinct actions: "Copiar respaldo",
      "Abrir ledger archivado…" (folder icon) and "Archivar y empezar un
      nuevo libro" (archive icon) — the two archive actions are clearly
      different at a glance.
- [ ] "Abrir ledger archivado…" opens a file picker that accepts any `.db`
      file, including one outside the app's own data folder.
- [ ] Opening the archived file from step 1 shows the archived ledger's
      historical data in every screen (Ventas, Catálogo, Reponer stock,
      Gastos, Fiado, Arqueo) and the balance banner reflects the archived
      ledger's own balance, not the live one's.
- [ ] The header bar swaps to a hard-to-miss "SOLO LECTURA — <archived file
      name>" banner (deep orange) while browsing the archive; the balance
      banner remains visible below it.
- [ ] No write control is visible on any screen while read-only: no
      "Agregar al carrito"/"Registrar venta", no edit/void icons on sales or
      expenses, no "Crear producto"/"Cambiar precio"/deactivate, no
      "Registrar reposición", no "Marcar pagado"/"Abono parcial", no
      "Registrar arqueo". Lists and history stay fully readable.
- [ ] The menu while in archive mode shows only "Cerrar ledger archivado" —
      the backup, open-archive and archive-and-new-ledger actions are hidden.
- [ ] Exportar still works from the archived view and the resulting workbook
      matches the archived ledger's own figures.

## Cerrar ledger archivado

- [ ] "Cerrar ledger archivado" restores the live ledger immediately: the
      user bar returns, the balance banner shows the live ledger's balance
      again, and all six screens show live data — no app restart needed.
- [ ] After closing, the original archived file is byte-for-byte identical
      to before the open → browse → export → close cycle (compare with a
      checksum), and the live ledger file is untouched too.
- [ ] Re-opening the same archived file works again (the temp copy is
      recreated from the untouched original).
- [ ] Opening a `.db` file created by a newer app version shows the Spanish
      error "Este archivo pertenece a una versión más nueva de la app y no
      puede abrirse." and leaves the file untouched.

---

# Manual QA Checklist — Plan #5 (Audit Trail Screen and Windows CI Build)

Walk through this checklist by hand against a running app
(`uv run flet run`) before considering the Plan #5 PR ready for review. Note
the results (passed / issue observed + steps to reproduce) in the PR
description.

Setup: use a dev ledger with a mix of history — several products (create,
change price), restocks (some with linked expense), cash/QR/credit sales,
some edited and some voided, debt payments (mark paid + abono), expenses
(create/edit/void), and cash counts. Working from the archive setup of Plan
#4 also exercises the screen against a read-only session.

## Auditoría — filters

- [ ] The nav rail shows a seventh destination, "Auditoría", after Exportar.
- [ ] Opening the screen defaults to "Últimas 24 horas" and shows the count
      line ("N cambios encontrados") plus the event list, newest first, with
      timestamp, category badge, change-type badge, user and summary.
- [ ] **Tiempo**: switching between Última hora / 24 horas / 7 días / 30 días /
      Todo changes the list and the count immediately, and resets to the
      first page.
- [ ] **Usuario**: "Todos" shows everyone; selecting one user shows only that
      user's changes (try an inactive user who made changes earlier).
- [ ] **Categoría**: "Todas" selects every category; deselecting individual
      chips narrows the list (e.g. only Ventas, only Gastos). An empty
      selection behaves like "Todas".
- [ ] **Tipo de cambio**: same multi-select behavior for Registro / Edición /
      Eliminación. Selecting only "Eliminación" shows only voided sales and
      expenses (never products/batches/fiado/arqueo).
- [ ] Combined filters narrow correctly (e.g. Usuario=Ana + Categoría=Ventas
      + Tipo=Edición shows only her edited sales).
- [ ] Filtering by "Todo" with a long-running ledger still paginates — the
      screen does not hang or silently drop old events.
- [ ] Badges are visually distinct: registro neutral, edición amber,
      eliminación red.
- [ ] No create/edit/void/mark-paid control exists on the screen, in both a
      live session and an archived (read-only) session.

## Auditoría — pagination and detail (Task 4)

- [ ] With more than 50 matching events, "Cargar más" appends the next page
      without duplicates, until the whole filtered set is loaded.
- [ ] Edited/voided sales and expenses show "Ver detalle"; expanding an
      edited sale shows the changed quantities / total / payment before→after
      (e.g. "Cantidad 'Coca-Cola 600ml': 2 → 3"), and an edited expense shows
      description/total before→after. A reassigned sale shows the user
      change. Voided rows show "Antes de anular:" with what was voided.
- [ ] Registro rows and non-editable categories have no detail button.
- [ ] No summary or detail text anywhere mentions `logical_id`, `version`,
      `superseded_at` or `deleted_at`.

## Auditoría — Excel exports

- [ ] **General export (Exportar screen)**: the workbook now has a fifth
      "Auditoría" sheet listing every event in the chosen date range with
      category, change type, date, user and the same summary sentences the
      screen shows for "Todo/Todos/Todas" over that range.
- [ ] **"Exportar esta vista"** (Auditoría screen): with filters applied
      (e.g. one user + last 7 days), the button saves a single-sheet workbook
      containing exactly the filtered events — hand it to someone as
      "everything Juan touched in the last 7 days". Success/error messaging
      matches the export screen's pattern.

## Windows CI build (Task 6)

- [ ] A push to `main` (or a `v*` tag) produces a `build-windows` job in the
      Actions run that succeeds and uploads the `sdb-caja-chica-windows`
      artifact. (This is a manual smoke check in place of the still-deferred
      QEMU boot verification from `plan-03.md` Task 6.)
- [ ] Download the artifact, extract, and run `sdb_caja_chica.exe` on a
      Windows machine: the user picker appears, a sale can be recorded, and
      the balance banner updates. The ledger is created under the user's
      Documents folder, not next to the executable.
- [ ] A push to a feature branch / PR does **not** trigger the build job —
      only the test job runs.
