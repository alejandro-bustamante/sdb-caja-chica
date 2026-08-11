# Manual QA Checklist — Plan #2 (Daily-Use UI Screens)

Walk through every checklist below by hand against a running app
(`uv run flet run`) before considering the Plan #2 PR ready for review. Note
the results (passed / issue observed + steps to reproduce) in the PR
description.

Plan #3 (Excel export, backup, archive-and-new-ledger, packaging) will append
its own checklist here rather than replace this file.

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
- [ ] Editing/voiding a credit sale that already has debt collections is
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
