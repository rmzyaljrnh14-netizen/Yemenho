-- 008_quality.sql — quality and patient-safety modules (v0.7).
--
-- Modules: incident reporting, root-cause analysis (RCA), corrective and
-- preventive actions (CAPA), risk register, internal audits, improvement
-- plans, quality documents and quality meetings.
--
-- All tables are hospital-scoped and protected by RLS through
-- app_can_see_hospital (defined in 005_indicators.sql). Reference catalogues
-- (severity, categories) are typed text columns with CHECK constraints so the
-- data stays structured and the API can decide on codes, never on English text.
--
-- Every table carries created_at/updated_at and a soft-delete marker, so the
-- sync engine can treat them uniformly and nothing is ever hard-deleted.

-- ---------------------------------------------------------------------------
-- Incidents (إبلاغ عن الحوادث والأخطاء الطبية)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
    id                  uuid PRIMARY KEY,
    hospital_id         uuid NOT NULL REFERENCES hospitals(id),
    department_id       uuid REFERENCES departments(id),
    code                text NOT NULL,                 -- human reference, e.g. INC-2026-0001
    title               text NOT NULL,
    description         text,
    incident_type       text NOT NULL DEFAULT 'other'
        CHECK (incident_type IN (
            'medication','fall','pressure_ulcer','infection','surgical',
            'diagnostic','transfusion','equipment','behaviour','other')),
    severity            text NOT NULL DEFAULT 'moderate'
        CHECK (severity IN ('near_miss','minor','moderate','major','catastrophic')),
    patient_harm        text NOT NULL DEFAULT 'none'
        CHECK (patient_harm IN ('none','mild','moderate','severe','death')),
    occurred_at         timestamptz,
    reported_at         timestamptz NOT NULL DEFAULT now(),
    reported_by         uuid,
    is_anonymous        boolean NOT NULL DEFAULT false,
    status              text NOT NULL DEFAULT 'reported'
        CHECK (status IN ('reported','under_review','rca','capa','closed','rejected')),
    -- free-text actions taken immediately, before formal RCA
    immediate_action    text,
    closed_at           timestamptz,
    closed_by           uuid,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    deleted_at          timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_code
  ON incidents (hospital_id, code) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_incidents_hospital_status ON incidents (hospital_id, status);

-- ---------------------------------------------------------------------------
-- Root-cause analysis (تحليل الأسباب الجذرية RCA)
-- One RCA per incident. The five-whys / fishbone material is kept as typed
-- rows in incident_rca_causes so it can be reported on, not as a blob.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incident_rca (
    id                uuid PRIMARY KEY,
    incident_id       uuid NOT NULL REFERENCES incidents(id),
    hospital_id       uuid NOT NULL REFERENCES hospitals(id),
    status            text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','completed','cancelled')),
    method            text NOT NULL DEFAULT 'five_whys'
        CHECK (method IN ('five_whys','fishbone','fault_tree','other')),
    team_ar           text,          -- team members (names are personal data: demo only)
    timeline_ar       text,          -- sequence of events
    findings_ar       text,          -- what was found
    started_at        timestamptz NOT NULL DEFAULT now(),
    completed_at      timestamptz,
    facilitator_id    uuid,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rca_per_incident
  ON incident_rca (incident_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS incident_rca_causes (
    id            uuid PRIMARY KEY,
    rca_id        uuid NOT NULL REFERENCES incident_rca(id),
    category      text NOT NULL DEFAULT 'other'
        CHECK (category IN (
            'patient','staff','communication','equipment','environment',
            'process','management','training','other')),
    description_ar text NOT NULL,
    is_root_cause  boolean NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);

-- ---------------------------------------------------------------------------
-- CAPA (الإجراءات التصحيحية والوقائية)
-- May be linked to an incident and/or an RCA, or stand alone (e.g. from an audit).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS capa_actions (
    id                uuid PRIMARY KEY,
    hospital_id       uuid NOT NULL REFERENCES hospitals(id),
    department_id     uuid REFERENCES departments(id),
    incident_id       uuid REFERENCES incidents(id),
    rca_id            uuid REFERENCES incident_rca(id),
    audit_id          uuid,                    -- FK added after quality_audits below
    kind              text NOT NULL DEFAULT 'corrective'
        CHECK (kind IN ('corrective','preventive')),
    title             text NOT NULL,
    description_ar    text,
    owner_user_id     uuid,
    owner_name_ar     text,
    due_date          date,
    priority          text NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low','medium','high','critical')),
    status            text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','done','verified','cancelled')),
    completion_note_ar text,
    completed_at      timestamptz,
    verified_at       timestamptz,
    verified_by       uuid,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz
);

CREATE INDEX IF NOT EXISTS ix_capa_hospital_status ON capa_actions (hospital_id, status);
CREATE INDEX IF NOT EXISTS ix_capa_due ON capa_actions (hospital_id, due_date);

-- ---------------------------------------------------------------------------
-- Risk register (إدارة المخاطر)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risks (
    id                uuid PRIMARY KEY,
    hospital_id       uuid NOT NULL REFERENCES hospitals(id),
    department_id     uuid REFERENCES departments(id),
    code              text NOT NULL,
    title             text NOT NULL,
    description_ar    text,
    category          text NOT NULL DEFAULT 'clinical'
        CHECK (category IN (
            'clinical','medication','infection','environment','equipment',
            'staffing','information','security','other')),
    likelihood        integer NOT NULL DEFAULT 3 CHECK (likelihood BETWEEN 1 AND 5),
    impact            integer NOT NULL DEFAULT 3 CHECK (impact BETWEEN 1 AND 5),
    -- risk score is a generated column so it can never drift from its inputs
    score             integer GENERATED ALWAYS AS (likelihood * impact) STORED,
    mitigation_ar     text,
    owner_user_id     uuid,
    owner_name_ar     text,
    review_date       date,
    status            text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','mitigated','accepted','closed')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_risk_code
  ON risks (hospital_id, code) WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------------------
-- Internal audits (التدقيق الداخلي)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_audits (
    id                uuid PRIMARY KEY,
    hospital_id       uuid NOT NULL REFERENCES hospitals(id),
    department_id     uuid REFERENCES departments(id),
    code              text NOT NULL,
    title             text NOT NULL,
    standard_ar       text,                 -- e.g. national patient-safety standard
    scope_ar          text,
    auditor_name_ar   text,
    audit_date        date,
    status            text NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','in_progress','completed','closed')),
    score             numeric,              -- 0..100 compliance score
    findings_ar       text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_code
  ON quality_audits (hospital_id, code) WHERE deleted_at IS NULL;

-- Now that quality_audits exists, wire the CAPA link (kept loose to avoid a
-- circular dependency at table-creation time).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'capa_actions_audit_id_fkey'
    ) THEN
        ALTER TABLE capa_actions
            ADD CONSTRAINT capa_actions_audit_id_fkey
            FOREIGN KEY (audit_id) REFERENCES quality_audits(id);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Improvement plans (خطط التحسين) and their tracked actions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS improvement_plans (
    id                uuid PRIMARY KEY,
    hospital_id       uuid NOT NULL REFERENCES hospitals(id),
    department_id     uuid REFERENCES departments(id),
    code              text NOT NULL,
    title             text NOT NULL,
    objective_ar      text,
    baseline_ar       text,
    target_ar         text,
    indicator_id      uuid REFERENCES indicators(id),
    owner_name_ar     text,
    start_date        date,
    due_date          date,
    status            text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','active','completed','cancelled')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_improvement_code
  ON improvement_plans (hospital_id, code) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS improvement_actions (
    id            uuid PRIMARY KEY,
    plan_id       uuid NOT NULL REFERENCES improvement_plans(id),
    title         text NOT NULL,
    owner_name_ar text,
    due_date      date,
    status        text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','done','cancelled')),
    note_ar       text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);

-- ---------------------------------------------------------------------------
-- Quality documents and policies (وثائق وسياسات الجودة)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_documents (
    id                uuid PRIMARY KEY,
    hospital_id       uuid NOT NULL REFERENCES hospitals(id),
    code              text NOT NULL,
    title             text NOT NULL,
    doc_type          text NOT NULL DEFAULT 'policy'
        CHECK (doc_type IN ('policy','procedure','guideline','form','record','other')),
    version           text NOT NULL DEFAULT '1.0',
    status            text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','under_review','approved','obsolete')),
    summary_ar        text,
    owner_name_ar     text,
    effective_date    date,
    review_date       date,
    approved_by       uuid,
    approved_at       timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_code
  ON quality_documents (hospital_id, code, version) WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------------------
-- Quality meetings and their decisions (اجتماعات الجودة وقراراتها)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_meetings (
    id                uuid PRIMARY KEY,
    hospital_id       uuid NOT NULL REFERENCES hospitals(id),
    title             text NOT NULL,
    meeting_date      date,
    location_ar       text,
    chair_name_ar     text,
    attendees_ar      text,
    agenda_ar         text,
    minutes_ar        text,
    status            text NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled','held','cancelled')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz
);

CREATE TABLE IF NOT EXISTS quality_meeting_decisions (
    id            uuid PRIMARY KEY,
    meeting_id    uuid NOT NULL REFERENCES quality_meetings(id),
    decision_ar   text NOT NULL,
    owner_name_ar text,
    due_date      date,
    status        text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','done','cancelled')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);

-- ---------------------------------------------------------------------------
-- Row-level security: every quality table is hospital-scoped.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'incidents','incident_rca','capa_actions','risks','quality_audits',
        'improvement_plans','quality_documents','quality_meetings'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_iso', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I USING (app_can_see_hospital(hospital_id))',
            t || '_iso', t
        );
    END LOOP;
END $$;

-- Child tables inherit their parent's scope through the parent hospital.
ALTER TABLE incident_rca_causes ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_rca_causes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS incident_rca_causes_iso ON incident_rca_causes;
CREATE POLICY incident_rca_causes_iso ON incident_rca_causes
  USING (rca_id IN (SELECT r.id FROM incident_rca r WHERE app_can_see_hospital(r.hospital_id)));

ALTER TABLE improvement_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE improvement_actions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS improvement_actions_iso ON improvement_actions;
CREATE POLICY improvement_actions_iso ON improvement_actions
  USING (plan_id IN (
    SELECT p.id FROM improvement_plans p WHERE app_can_see_hospital(p.hospital_id)
  ));

ALTER TABLE quality_meeting_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE quality_meeting_decisions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS quality_meeting_decisions_iso ON quality_meeting_decisions;
CREATE POLICY quality_meeting_decisions_iso ON quality_meeting_decisions
  USING (meeting_id IN (
    SELECT m.id FROM quality_meetings m WHERE app_can_see_hospital(m.hospital_id)
  ));
