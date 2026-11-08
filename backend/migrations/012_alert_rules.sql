-- 012_alert_rules.sql — configurable alert thresholds (v0.10).
--
-- The alert engine (v0.8/v0.9) used fixed thresholds. This table makes the
-- numeric thresholds *data*: a national default row (hospital_id IS NULL) and,
-- optionally, a per-hospital override. Nothing else about an alert is stored —
-- the alert list is still computed on every read.
--
-- A row holds only the parameters that differ from the code defaults; the
-- effective value is the code default overlaid by the national row and then by
-- the hospital row. Unknown keys are ignored and out-of-range values are
-- clamped by the service, so a bad edit can never break the engine.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS alert_rules (
    id          uuid PRIMARY KEY,
    hospital_id uuid REFERENCES hospitals(id),
    kind        text NOT NULL,
    params      jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_enabled  boolean NOT NULL DEFAULT true,
    note_ar     text,
    updated_by  uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    deleted_at  timestamptz
);

-- One live national default per kind, and one live override per hospital+kind.
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_rules_national
  ON alert_rules (kind) WHERE hospital_id IS NULL AND deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_rules_hospital
  ON alert_rules (hospital_id, kind) WHERE hospital_id IS NOT NULL AND deleted_at IS NULL;

ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_rules FORCE ROW LEVEL SECURITY;
-- National defaults (hospital_id IS NULL) are visible to everyone; an override is
-- visible only to callers who may see that hospital.
DROP POLICY IF EXISTS alert_rules_iso ON alert_rules;
CREATE POLICY alert_rules_iso ON alert_rules
  USING (hospital_id IS NULL OR app_can_see_hospital(hospital_id));

-- Permission: changing thresholds is a deliberate management act.
INSERT INTO permissions (id, code, name_ar) VALUES
  ('01900000-0000-7001-8000-00000000000f', 'alert.configure', 'تهيئة قواعد التنبيه وعتباتها')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
  ('central_admin',   'alert.configure'),
  ('hospital_manager','alert.configure'),
  ('quality_manager', 'alert.configure')
) AS m(role_code, perm_code)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = m.perm_code
ON CONFLICT DO NOTHING;

-- Seed the national defaults so the catalogue lives in the database (data over
-- code). Values match the engine's original constants exactly.
INSERT INTO alert_rules (id, hospital_id, kind, params, note_ar)
VALUES
  ('01900000-0000-7002-8000-000000000001', NULL, 'low_compliance',
   '{"warn_below": 85, "high_below": 70}'::jsonb, 'الافتراضي الوطني'),
  ('01900000-0000-7002-8000-000000000002', NULL, 'anomaly',
   '{"z_threshold": 3.5, "min_points": 4}'::jsonb, 'الافتراضي الوطني'),
  ('01900000-0000-7002-8000-000000000003', NULL, 'trend',
   '{"min_points": 3}'::jsonb, 'الافتراضي الوطني'),
  ('01900000-0000-7002-8000-000000000004', NULL, 'high_risk',
   '{"score_threshold": 15}'::jsonb, 'الافتراضي الوطني'),
  ('01900000-0000-7002-8000-000000000005', NULL, 'overdue_capa',
   '{"grace_days": 0}'::jsonb, 'الافتراضي الوطني'),
  ('01900000-0000-7002-8000-000000000006', NULL, 'open_incidents',
   '{"min_count": 1}'::jsonb, 'الافتراضي الوطني'),
  ('01900000-0000-7002-8000-000000000007', NULL, 'open_rca',
   '{"min_count": 1}'::jsonb, 'الافتراضي الوطني')
ON CONFLICT DO NOTHING;
