-- 011_alerts.sql — unified alert centre (v0.9).
--
-- The alert list itself is *computed* on the fly from stored rows by the
-- deterministic insight engine (app/services/alerts.py), so an alert can never
-- drift from the data it describes. Only the acknowledgement is persisted here:
-- who saw which alert, when, and with what note.
--
-- An alert is identified by a stable `alert_key` (a hash of its kind, hospital
-- and period), so the same alert keeps its identity when the list is recomputed
-- on a later day. Row-level security scopes acknowledgements to the hospitals a
-- caller may see, exactly like the rest of the API.
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS alert_acknowledgements (
    id              uuid PRIMARY KEY,
    alert_key       text NOT NULL,
    hospital_id     uuid NOT NULL REFERENCES hospitals(id),
    period_year     integer NOT NULL,
    period_month    integer,
    kind            text NOT NULL,
    severity        text NOT NULL
        CHECK (severity IN ('high','medium','info')),
    note_ar         text,
    acknowledged_by uuid,
    acknowledged_at timestamptz NOT NULL DEFAULT now(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz
);

-- One live acknowledgement per alert key. Re-acknowledging updates the note
-- instead of adding a row; reopening soft-deletes it so history is never lost.
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_ack_key
  ON alert_acknowledgements (alert_key) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_alert_ack_hospital
  ON alert_acknowledgements (hospital_id, period_year, period_month);

ALTER TABLE alert_acknowledgements ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_acknowledgements FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS alert_acknowledgements_iso ON alert_acknowledgements;
CREATE POLICY alert_acknowledgements_iso ON alert_acknowledgements
  USING (app_can_see_hospital(hospital_id));

-- Permission: acknowledging an alert is a deliberate management act, so it is
-- separate from merely viewing the list (which reuses report.view).
INSERT INTO permissions (id, code, name_ar) VALUES
  ('01900000-0000-7001-8000-00000000000e', 'alert.manage', 'إدارة التنبيهات (الإقرار وإعادة الفتح)')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
  ('central_admin',   'alert.manage'),
  ('gov_officer',     'alert.manage'),
  ('hospital_manager','alert.manage'),
  ('quality_manager', 'alert.manage')
) AS m(role_code, perm_code)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = m.perm_code
ON CONFLICT DO NOTHING;
