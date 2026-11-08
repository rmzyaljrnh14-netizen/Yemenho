-- 015_sync_alerts.sql — national defaults for the sync-health alert kinds (v0.13).
--
-- The alert engine can now raise two sync findings: a hospital device that has
-- not synced for too long, and unreviewed sync conflicts. Their thresholds are
-- ordinary configurable alert rules (v0.10), so seed the national default rows
-- here to keep the catalogue in the database (data over code).
--
-- Idempotent: safe to re-run.

INSERT INTO alert_rules (id, hospital_id, kind, params, note_ar)
VALUES
  ('01900000-0000-7002-8000-000000000008', NULL, 'stale_device',
   '{"stale_days": 7}'::jsonb, 'الافتراضي الوطني'),
  ('01900000-0000-7002-8000-000000000009', NULL, 'open_conflict',
   '{"min_count": 1}'::jsonb, 'الافتراضي الوطني')
ON CONFLICT DO NOTHING;
