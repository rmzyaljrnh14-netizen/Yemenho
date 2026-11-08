-- 009_incident_sync.sql — make incidents syncable (v0.7).
--
-- The desktop app must be able to report a patient-safety incident while
-- offline. Incidents therefore join the sync protocol in docs/14: they carry a
-- revision counter so a stale push is detected as a conflict instead of
-- silently overwriting, and the change_log already records their hospital scope.

ALTER TABLE incidents ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;
