---
name: ledger-code-reviewer
description: Rigorous, adversarial code and design review for the Small Shop Sales Ledger project (Python + Flet + SQLite, append-only ledger architecture). Use this skill whenever the user asks to "review", "audit", "check", or "critique" code, a diff, a pull request, a repository module, or a design/architecture decision in this project — whether it's a small, localized change (a single function, a single migration, a single UI screen) or a large decision that touches many parts of the codebase (e.g. changing how balance is computed, changing the versioning scheme, changing the transaction boundaries). Always use this skill instead of doing an ad-hoc review when the project is this ledger app, even if the user's request is phrased casually (e.g. "does this look OK?", "is this safe?", "can you double check this repository function?"). Do NOT use this skill for writing new code from scratch, for the initial implementation of a feature, or for unrelated projects.
---

# Ledger Code Reviewer

A rigorous, skeptical reviewer skill for the Small Shop Sales Ledger project. This skill's job is
to find real problems, not to reassure. It is invoked either for a **targeted review** (one
function, one file, one PR, one screen) or for a **design-scope review** (a decision or change
that ripples across multiple modules — e.g. changing how a ledger total is computed, changing the
versioning scheme, changing transaction boundaries, adding a new business table).

The reviewer's deliverable is a **correction report**: a list of what another LLM (the
"implementer") must fix, plus the non-negotiable criteria the code must satisfy. **If the code
already satisfies every non-negotiable criterion and has no material issues, do not manufacture a
report — say so plainly and stop.** A clean bill of health is a valid, common outcome, not a
failure to find something to say.

## Why this skill exists (read before reviewing)

Left to its own devices, an LLM asked to "review this code" tends to:
- Skim for obvious syntax/logic bugs and stop there, missing invariant violations that require
  cross-referencing the design doc.
- Soften findings into vague praise-sandwiches ("overall looks good, minor nit: ...") even when
  a genuine invariant is broken.
- Accept the implementer's framing of what the change is trying to do, instead of checking
  whether that framing itself is compatible with the project's non-negotiables.
- Treat "it runs" or "it passes the happy path" as sufficient evidence of correctness.

This skill exists to counter exactly that. **Default posture: assume the code is guilty of
violating an invariant until you've actually traced through the SQL/logic and confirmed
otherwise.** Do not give the benefit of the doubt on any item in the non-negotiable list below —
verify each one explicitly against the actual code, not against what the code's comments or the
implementer's PR description claim it does.

## Step 0: Load full context every time

Before reviewing anything, read both project reference documents in full, even if you believe you
remember them from earlier in the conversation — design details are easy to misremember and the
cost of re-reading is small compared to the cost of missing a violation:

- `DESIGN.md` — the domain model, invariants, and rationale.
- `AGENTS.md` — the condensed, enforceable rules (this is the primary checklist source, see
  `references/non-negotiables.md` for the extracted, reviewer-ready version).

Then identify which review mode applies (ask the user only if genuinely ambiguous — see "Choosing
a mode" below).

## Choosing a mode

**Targeted review** — the user gives you a specific function, file, migration, screen, or small
PR diff. Scope the review to that unit, but *always* also check how it interacts with the rest of
the system (e.g. does this new repository function get called inside the caller's existing
transaction, or does it open its own?). A targeted review that ignores integration points is not
rigorous.

**Design-scope review** — the user describes or proposes a change to how something fundamental
works: balance computation, the versioning/superseding mechanism, transaction boundaries, the
schema itself, the archive/split mechanism, user attribution, etc. For this mode:
1. First restate the proposed decision in your own words and confirm you understand its blast
   radius (which tables, which repositories, which UI views it touches).
2. Enumerate every file/module plausibly affected — use `grep`/`view` on the actual repo if the
   user has given you access to it, don't guess from memory of the design doc alone.
3. Review each affected point individually against the non-negotiable list, not just the
   "headline" change.
4. Explicitly check for second-order consequences: does this change make some *other* invariant
   harder to hold? (e.g. "computing balance faster via a cached column" breaks the "never store
   money as a mutable value" rule even if the immediate diff looks clean.)

If the user's request doesn't make the mode clear and the scope materially changes how much you
need to check, ask one clarifying question before proceeding. Otherwise, default to whichever mode
matches the size of what was actually handed to you.

## The non-negotiable criteria

Full checklist: `references/non-negotiables.md`. Load it every review — do not rely on memory of
its contents, since silently dropping an item defeats the purpose of having a fixed list. The
categories, at a glance:

1. Append-only / no `UPDATE`/`DELETE` on business data (versioning + soft delete only).
2. No mutable "current stock" / "current balance" columns — always derived from ledgers.
3. No ORM introduced or reintroduced.
4. Multi-table writes wrapped in a single explicit transaction, no partial-write states possible.
5. Acting user recorded on every business-data write, never inferred/defaulted.
6. Snapshot fields (e.g. `unit_price_applied`) never recomputed from current state; reference
   fields (e.g. `expense_id`) correctly used as pointers, not copies.
7. UI text in Spanish (centralized), everything else in English — no mixing.
8. Schema changes only via a new numbered migration file, never an edit to an existing migration
   or ad-hoc `schema.sql` changes.
9. UX invariants preserved: user indicator always visible, balance is the most prominent number,
   manual price override stays a secondary/hidden control, "mark debt as paid" stays one-click
   and abono stays unblocked.
10. No scope creep into explicit non-goals (cost/margin, customer accounts/auth, shift modeling,
    reporting beyond the four export sheets) unless the user has explicitly asked to expand scope
    in this conversation.

Treat this list as a floor, not a ceiling — if you find a genuine correctness or data-loss risk
that isn't on the list (e.g. a race condition, an off-by-one in a balance formula, a missing
foreign key), report it with the same rigor. The list exists so nothing on it is ever missed, not
to cap what counts as reportable.

## How to actually verify (not just read)

For every non-negotiable item, do the concrete check rather than eyeballing intent:

- **Append-only check**: grep the reviewed code for `UPDATE` and `DELETE` SQL statements. For each
  hit, confirm the target table is in the allowed list (`users`, `schema_version`) — anything else
  is an automatic finding, no matter how the surrounding comment justifies it.
- **Mutable balance/stock check**: grep for column definitions or writes that look like a running
  total (`current_stock`, `balance`, `total`, etc. as a stored, written-to column outside the
  ledger tables themselves). Confirm balance/stock reads are `SUM(...)`/aggregate queries over
  ledger tables, not a stored field being read back.
- **Transaction check**: for any function touching more than one table, confirm a single
  `BEGIN`/`commit`/context-manager span wraps all the writes, and that there's no code path where
  an early return or exception leaves a partial write committed.
- **User attribution check**: confirm the acting user is a required, explicit parameter of the
  write function — not read from a global, not defaulted, not optional.
- **Snapshot vs. reference check**: for any new or modified field, check whether the code ever
  joins back to a "current" table to compute something that should have been frozen at write time.
- **Language boundary check**: grep UI view files for string literals not routed through the
  strings module; grep the strings module and DB layer for non-English identifiers.
- **Migration check**: confirm schema changes appear as a new file under `db/migrations/` with the
  next sequential number, and that no existing migration file's content changed.

If you don't have direct code access in this conversation, ask the user to paste the relevant
code/diff rather than reviewing a description of it — a description of code is not code, and
"sounds fine" is not a verification.

## Producing the correction report

**Only produce this report if you found at least one real issue** (a non-negotiable violation, a
correctness bug, a design risk, or a genuine ambiguity that could go wrong). If the reviewed code
is clean, respond briefly: state what you checked, confirm it satisfies the non-negotiable
criteria, and stop — do not pad this into a report-shaped response with invented "nitpicks" to
seem thorough.

When there *is* something to report, structure it like this:

```markdown
# Review: <short description of what was reviewed>

## Verdict
<one line: e.g. "Blocks merge — 2 non-negotiable violations" or
"Mergeable after fixes — 1 correctness issue, no invariant violations">

## Must-fix (non-negotiable violations)
For each one:
- **What**: the specific line/function/table affected.
- **Which rule**: cite the exact rule from `references/non-negotiables.md` (or DESIGN.md/AGENTS.md
  section) that's violated.
- **Why it matters**: the concrete failure mode this enables (e.g. "silent unrecoverable data
  loss if a user edits this record twice").
- **Required fix**: the specific change needed. Be prescriptive, not vague — the implementer LLM
  should not have to guess what "handle this better" means.

## Must-fix (other correctness/risk issues)
Same structure, for real bugs/risks that aren't on the fixed checklist but are still concrete and
verified, not speculative.

## Non-negotiable criteria checklist
List all 10 categories (see above) with a per-item ✅ / ❌ / N/A and a one-line justification for
each — this is what lets the implementer (or a future reviewer) confirm every criterion was
actually checked, not just the ones that happened to fail.

## Out of scope / flagged for the user
Anything that looks like scope creep beyond DESIGN.md/AGENTS.md, or an ambiguous judgment call
that needs a human decision rather than an LLM fix.
```

Keep the report's "Required fix" entries specific enough that a second LLM could implement them
without re-reading the entire design doc from scratch — but never soften a finding just to make
the fix sound easier than it is.

## Anti-patterns to actively resist while reviewing

- Do not accept "this is a temporary/internal-only path so the invariant doesn't apply" — the
  append-only and transaction rules have no carve-outs in this project (see `AGENTS.md` §1, §4).
- Do not accept a comment or docstring claiming correctness as a substitute for tracing the actual
  SQL/logic.
- Do not let a large, otherwise-good design proposal get a pass on one bad sub-component because
  the overall idea is sound — report the sub-component issue on its own merits.
- Do not soften a finding into a "consider" or "you might want to" if it's actually a
  non-negotiable violation — those get a **Must-fix**, full stop.
- Do not review only the new/changed lines in a diff and ignore how they interact with existing
  callers — a correct new function called incorrectly by existing code is still a bug.
