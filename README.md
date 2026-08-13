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

## Web demo (static build, deploys to GitHub Pages)

The app can run entirely in the browser via Flet + Pyodide (the SQLite ledger
is in-memory per session, so the hosted demo is reset on every page load and
seeded fresh on first run by `app/db/demo_seed.py`).

```sh
uv run flet publish \
  --base-url /sdb-caja-chica/ \
  --route-url-strategy hash
```

This emits a static site under `dist/` (served at the repo's subpath). Deploy
it with the automated GitHub Pages workflow (`.github/workflows/pages.yml`) or
push `dist/` to a `gh-pages` branch / Pages-enabled repo root and configure
the base URL to match.

> Note: `flet publish` bundles the whole repo into the app archive — for a
> clean demo that always starts with the seeded sample data
> (`app/db/demo_seed.py`) and never your local scratch ledger, remove
> `dev-data/ledger.db` first. The demo runs with an in-memory copy of the DB,
> so nothing you do in the browser persists between visits.

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
