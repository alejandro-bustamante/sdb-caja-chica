# Small Shop Sales Ledger

A small desktop app (Python + Flet + SQLite) for tracking sales, stock,
expenses, and cash balance for a small shop. Full design and invariants live
in `DESIGN.md` and `AGENTS.md` — read both before making non-trivial changes.

## Install

```sh
uv sync
```

## Run

```sh
uv run python -m app.main
```

The app resolves its SQLite ledger under `Documents/<AppName>/<ledger-file>.db`
per `DESIGN.md` §5.3 when `SDB_CAJA_CHICA_DATA_DIR` is set. During local
development, when that var is unset, it writes to `./dev-data/` (kept out of
git), so local runs never touch your real Documents folder.

## Tests

```sh
uv run pytest
```

## Linting

The linter of choice is `ruff`:

```sh
uv run ruff check .
```

## Project layout

```
app/
  db/
    schema.sql          # reference copy of the current DB shape
    migrations/         # numbered migrations, source of truth for .db files
    connection.py       # connection, PRAGMAs, transaction helper, migration runner
    repositories/       # one module per entity, raw sqlite3, no ORM
  domain/
    balance.py          # derived stock/money calculations (pure SELECTs)
    validation.py       # framework-agnostic validators
  services/
    excel_export.py     # not yet implemented (see plan-01.md)
    backup.py           # not yet implemented (see plan-01.md)
  ui/
    views/              # one Flet view per screen
    components/         # shared widgets (user indicator bar, balance banner)
    strings_es.py       # all user-facing Spanish text, centralized
  main.py
tests/
```

## Conventions

- **Append-only business data**: sales, expenses, prices, stock and money are
  never `UPDATE`d or `DELETE`d — edits are new versions, deletions are soft
  deletes, and stock/balance are derived by summing ledgers at query time.
  See `AGENTS.md` §1.
- **No ORM**: raw `sqlite3` + a thin repository layer only.
- **Language**: code/identifiers/comments in English; every user-facing string
  is Spanish and lives only in `ui/strings_es.py`.
