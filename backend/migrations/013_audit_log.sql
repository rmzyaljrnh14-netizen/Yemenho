-- 013_audit_log.sql — audit-log access scope, immutability and query support (v0.11).
--
-- The audit log has existed since v0.1 and every sensitive action already writes
-- to it (app/services/identity.write_audit). What was missing was a *scope*: the
-- table carried no hospital_id, so it could not be isolated per hospital and had
-- no read API. This migration adds that scope and locks the table down.
--
-- Two properties matter for an audit log:
--   1. Isolation — a hospital user may only read their own hospital's entries,
--      a governorate office its governorate's, and central sees all. A row with
--      no hospital (logins, national library edits) is visible to central only.
--   2. Immutability — there is deliberately NO update or delete policy, so the
--      application role can neither alter nor erase a record once written.
--
-- The API supplies hospital_id explicitly when it writes (it knows the target
-- entity); the column is nullable for genuinely global events.
--
-- Idempotent: safe to re-run.

ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS hospital_id uuid REFERENCES hospitals(id);

-- Best-effort backfill for rows written before this column existed. Each row's
-- hospital is looked up through its entity when the entity is hospital-scoped.
UPDATE audit_log a SET hospital_id = h.id
  FROM hospitals h
 WHERE a.hospital_id IS NULL AND a.entity_type = 'hospital' AND h.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = d.hospital_id
  FROM departments d
 WHERE a.hospital_id IS NULL AND a.entity_type = 'department' AND d.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = p.hospital_id
  FROM reporting_periods p
 WHERE a.hospital_id IS NULL AND a.entity_type = 'reporting_period' AND p.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = p.hospital_id
  FROM indicator_values v
  JOIN reporting_periods p ON p.id = v.period_id
 WHERE a.hospital_id IS NULL AND a.entity_type = 'indicator_value' AND v.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = i.hospital_id
  FROM indicator_assignments i
 WHERE a.hospital_id IS NULL AND a.entity_type = 'indicator_assignment' AND i.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = i.hospital_id
  FROM incidents i
 WHERE a.hospital_id IS NULL AND a.entity_type = 'incident' AND i.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = r.hospital_id
  FROM incident_rca r
 WHERE a.hospital_id IS NULL AND a.entity_type = 'incident_rca' AND r.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = c.hospital_id
  FROM capa_actions c
 WHERE a.hospital_id IS NULL AND a.entity_type = 'capa_action' AND c.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = r.hospital_id
  FROM risks r
 WHERE a.hospital_id IS NULL AND a.entity_type = 'risk' AND r.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = q.hospital_id
  FROM quality_audits q
 WHERE a.hospital_id IS NULL AND a.entity_type = 'quality_audit' AND q.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = p.hospital_id
  FROM improvement_plans p
 WHERE a.hospital_id IS NULL AND a.entity_type = 'improvement_plan' AND p.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = d.hospital_id
  FROM quality_documents d
 WHERE a.hospital_id IS NULL AND a.entity_type = 'quality_document' AND d.id::text = a.entity_id;

UPDATE audit_log a SET hospital_id = m.hospital_id
  FROM quality_meetings m
 WHERE a.hospital_id IS NULL AND a.entity_type = 'quality_meeting' AND m.id::text = a.entity_id;

-- Query support: the API reads newest-first, filtered by time/actor/entity.
CREATE INDEX IF NOT EXISTS idx_audit_at          ON audit_log (at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_hospital_at ON audit_log (hospital_id, at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_at    ON audit_log (actor_user_id, at DESC);

-- Isolation for reads; broad permission for writes (an audit row is written in
-- many contexts, including login before a session scope exists). No UPDATE or
-- DELETE policy exists on purpose: with FORCE ROW LEVEL SECURITY the app role
-- simply cannot modify or erase a record.
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_log_read ON audit_log;
CREATE POLICY audit_log_read ON audit_log
  FOR SELECT
  USING (app_can_see_hospital(hospital_id));

DROP POLICY IF EXISTS audit_log_insert ON audit_log;
CREATE POLICY audit_log_insert ON audit_log
  FOR INSERT
  WITH CHECK (true);
