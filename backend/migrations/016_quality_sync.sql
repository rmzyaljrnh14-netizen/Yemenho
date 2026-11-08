-- 016_quality_sync.sql — make CAPA actions and risks syncable (v0.14).
--
-- The desktop app must be able to plan a corrective/preventive action and record
-- a risk while offline. Both join the sync protocol in docs/14: each carries a
-- revision counter so a stale push is detected as a conflict instead of silently
-- overwriting, and the change_log already records their hospital scope.
--
-- Idempotent: safe to re-run.

ALTER TABLE capa_actions ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;
ALTER TABLE risks ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;
