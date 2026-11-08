-- 017_audit_plan_sync.sql — make internal audits and improvement plans syncable (v0.15).
--
-- The desktop app must be able to open an internal audit and draft an
-- improvement plan (with its actions) while offline. All three join the sync
-- protocol in docs/14: each carries a revision counter so a stale push is
-- detected as a conflict instead of silently overwriting. The change_log
-- already records their hospital scope (improvement_actions resolve it through
-- their parent plan).
--
-- Idempotent: safe to re-run.

ALTER TABLE quality_audits      ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;
ALTER TABLE improvement_plans   ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;
ALTER TABLE improvement_actions ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;
