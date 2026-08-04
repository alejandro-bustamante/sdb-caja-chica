-- 0002: batches link to the expense's logical_id, not a physical version row.
--
-- The old `expense_id` pointed at one specific expenses row (a physical
-- version). If that expense was later edited or voided, the link went stale.
-- `expense_logical_id` is a plain reference column (not a FK — logical_id is
-- not unique across versions) resolved at read time to the current non-deleted
-- version of that logical_id.

ALTER TABLE batches ADD COLUMN expense_logical_id INTEGER;

-- Backfill from the expense the old link pointed to. logical_id is stable
-- across versions, so resolving the pointed-to row's logical_id keeps existing
-- batches linked to the correct expense.
UPDATE batches
SET expense_logical_id = (
    SELECT e.logical_id FROM expenses e WHERE e.id = batches.expense_id
)
WHERE expense_id IS NOT NULL;

ALTER TABLE batches DROP COLUMN expense_id;