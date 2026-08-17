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

## Windows build (CI)

The GitHub Actions workflow (`.github/workflows/ci.yml`) produces a Windows
`.exe` of the app. To keep iteration fast, the packaging step is deliberately
gated:

- **Tests and lint** run on every push and pull request.
- **`flet build windows`** runs only on pushes to `main` or on version tags
  (`v*`), because it downloads the Flutter SDK and performs a full native
  build — too slow for every commit.

### Getting the built .exe

1. Open the repository's **Actions** tab and pick the most recent `CI` run
   on `main` (or on a `v*` tag).
2. Under **Artifacts**, download `sdb-caja-chica-windows` — a zip of the
   `build/windows` output.
3. Extract it anywhere and run `sdb_caja_chica.exe` (the file name comes
   from `[project].name` in `pyproject.toml`).

The ledger file lives under the user's Documents folder on first launch
(`SDB_CAJA_CHICA_DATA_DIR` in `app/main.py`); the app writes nothing next to
the executable.

Use the artifact as a manual smoke check — boot it, pick a user, record a
sale, and confirm the balance banner moves. The QEMU boot-verification step
originally scoped in `plan-03.md` Task 6 remains deferred (not dropped); it
can be added before a first real release.

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
    excel_export.py     # 5-sheet Excel export (sales, expenses, debts, balance, auditoría)
    backup.py           # on-demand ledger backup + archive-and-new-ledger
  ui/
    views/              # one Flet view per screen (incl. Auditoría, plan-05)
    components/         # shared widgets (user indicator bar, balance banner)
    strings_es.py       # all user-facing Spanish text, centralized
  domain/
    audit.py            # read-only audit event query over the versioned tables
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
