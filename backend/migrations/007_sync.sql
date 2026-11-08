-- 007_sync.sql — offline sync substrate (v0.6).
--
-- Adds the server side of the sync protocol in docs/14:
--   * a per-record revision counter (rev) on the syncable, conflict-capable
--     tables, so a client can tell whether its base copy is stale;
--   * a monotonic change_log (server_seq) the client pulls from, using a
--     cursor, so it only receives what changed since it last synced;
--   * sync_idempotency so a re-sent batch (same op_id) is never applied twice;
--   * conflict_log so a stale write is recorded rather than silently lost;
--   * sync_nodes so the ministry can see which hospital device last synced.
--
-- Payloads in change_log are the full row state so the client can upsert
-- locally without extra round-trips. National reference rows (the indicator
-- library) carry hospital_id = NULL and are visible to every node.

-- ---------------------------------------------------------------------------
-- Revision counters on syncable tables
-- ---------------------------------------------------------------------------
ALTER TABLE reporting_periods ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;
ALTER TABLE indicator_values  ADD COLUMN IF NOT EXISTS rev bigint NOT NULL DEFAULT 1;

-- ---------------------------------------------------------------------------
-- Monotonic change sequence + change log
-- ---------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS change_log_seq;

CREATE TABLE IF NOT EXISTS change_log (
    server_seq  bigint PRIMARY KEY DEFAULT nextval('change_log_seq'),
    entity_type text NOT NULL,
    entity_id   text NOT NULL,
    op          text NOT NULL DEFAULT 'upsert' CHECK (op IN ('upsert', 'delete')),
    rev         bigint NOT NULL DEFAULT 1,
    -- NULL means national reference data, visible to every node.
    hospital_id uuid REFERENCES hospitals(id),
    payload     jsonb,
    at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_change_log_seq      ON change_log(server_seq);
CREATE INDEX IF NOT EXISTS idx_change_log_hospital ON change_log(hospital_id, server_seq);
CREATE INDEX IF NOT EXISTS idx_change_log_entity   ON change_log(entity_type, entity_id);

-- ---------------------------------------------------------------------------
-- Idempotency: one row per applied op_id (see docs/14 §7)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_idempotency (
    op_id       text PRIMARY KEY,
    node_id     text,
    hospital_id uuid REFERENCES hospitals(id),
    status      text NOT NULL,          -- applied | conflict | rejected
    result      jsonb NOT NULL,         -- the exact result returned the first time
    at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sync_idem_hospital ON sync_idempotency(hospital_id);

-- ---------------------------------------------------------------------------
-- Conflict log (see docs/14 §6.3)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conflict_log (
    id             uuid PRIMARY KEY,
    entity_type    text NOT NULL,
    entity_id      text NOT NULL,
    node_id        text,
    hospital_id    uuid REFERENCES hospitals(id),
    local_payload  jsonb,               -- the hospital's (stale) version
    server_payload jsonb,               -- the authoritative version on the server
    resolution     text NOT NULL,       -- auto_server | rejected | manual
    resolved_by    uuid,
    resolved_at    timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conflict_hospital ON conflict_log(hospital_id, created_at);

-- ---------------------------------------------------------------------------
-- Node registry (which device synced when)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_nodes (
    node_id      text PRIMARY KEY,
    hospital_id  uuid REFERENCES hospitals(id),
    name         text,
    last_seq     bigint NOT NULL DEFAULT 0,
    last_seen_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Row-level security: a node sees national rows plus its own hospital's rows.
-- ---------------------------------------------------------------------------
ALTER TABLE change_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE change_log       FORCE ROW LEVEL SECURITY;
ALTER TABLE sync_idempotency ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_idempotency FORCE ROW LEVEL SECURITY;
ALTER TABLE conflict_log     ENABLE ROW LEVEL SECURITY;
ALTER TABLE conflict_log     FORCE ROW LEVEL SECURITY;
ALTER TABLE sync_nodes       ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_nodes       FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS change_log_iso ON change_log;
CREATE POLICY change_log_iso ON change_log
  USING (hospital_id IS NULL OR app_can_see_hospital(hospital_id))
  WITH CHECK (hospital_id IS NULL OR app_can_see_hospital(hospital_id));

DROP POLICY IF EXISTS sync_idempotency_iso ON sync_idempotency;
CREATE POLICY sync_idempotency_iso ON sync_idempotency
  USING (hospital_id IS NULL OR app_can_see_hospital(hospital_id))
  WITH CHECK (hospital_id IS NULL OR app_can_see_hospital(hospital_id));

DROP POLICY IF EXISTS conflict_log_iso ON conflict_log;
CREATE POLICY conflict_log_iso ON conflict_log
  USING (hospital_id IS NULL OR app_can_see_hospital(hospital_id))
  WITH CHECK (hospital_id IS NULL OR app_can_see_hospital(hospital_id));

DROP POLICY IF EXISTS sync_nodes_iso ON sync_nodes;
CREATE POLICY sync_nodes_iso ON sync_nodes
  USING (hospital_id IS NULL OR app_can_see_hospital(hospital_id))
  WITH CHECK (hospital_id IS NULL OR app_can_see_hospital(hospital_id));

-- ---------------------------------------------------------------------------
-- Seed the change log with the current national indicator library so a fresh
-- node gets the library on its first pull.
-- ---------------------------------------------------------------------------
INSERT INTO change_log (entity_type, entity_id, op, rev, hospital_id, payload)
SELECT 'indicator', i.id::text, 'upsert', 1, NULL,
       jsonb_build_object(
         'id', i.id, 'code', i.code, 'name_ar', i.name_ar,
         'definition_ar', i.definition_ar, 'purpose_ar', i.purpose_ar,
         'calculation_ar', i.calculation_ar, 'computation', i.computation,
         'unit_ar', i.unit_ar, 'data_source_ar', i.data_source_ar,
         'frequency', i.frequency, 'responsible_party_ar', i.responsible_party_ar,
         'direction', i.direction, 'target_value', i.target_value,
         'acceptable_min', i.acceptable_min, 'acceptable_max', i.acceptable_max,
         'multiplier', i.multiplier, 'numerator_label_ar', i.numerator_label_ar,
         'denominator_label_ar', i.denominator_label_ar, 'is_active', i.is_active
       )
FROM indicators i
WHERE i.deleted_at IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM change_log c
    WHERE c.entity_type = 'indicator' AND c.entity_id = i.id::text
  );
