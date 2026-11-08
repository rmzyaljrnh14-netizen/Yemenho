-- 005_indicators.sql — national indicator library, assignments, reporting
-- periods and indicator values (v0.4).
--
-- Design notes:
--   * indicators is national reference data: readable by everyone, writable by
--     holders of indicator.manage (enforced in the API layer, not by RLS).
--   * indicator_assignments / reporting_periods / indicator_values /
--     indicator_value_revisions are hospital-scoped and protected by RLS.

-- ---------------------------------------------------------------------------
-- Helper: can the current request see a given hospital?
-- Central sees all; a governorate user sees its hospitals; a hospital user sees
-- only its own hospital.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app_can_see_hospital(h uuid) RETURNS boolean AS $$
  SELECT app_is_central()
      OR h::text = nullif(app_hospital_id(), '')
      OR h IN (
        SELECT x.id FROM hospitals x
        WHERE x.governorate_id::text = nullif(app_governorate_id(), '')
      )
$$ LANGUAGE sql STABLE;

-- ---------------------------------------------------------------------------
-- National indicator library
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indicators (
    id                    uuid PRIMARY KEY,
    code                  text UNIQUE NOT NULL,
    name_ar               text NOT NULL,
    definition_ar         text,
    purpose_ar            text,
    calculation_ar        text,                     -- how it is measured, prose
    computation           text NOT NULL DEFAULT 'entered'
        CHECK (computation IN ('ratio','rate','percent','count','average','sum','entered')),
    unit_ar               text,
    data_source_ar        text,
    frequency             text NOT NULL DEFAULT 'monthly'
        CHECK (frequency IN ('monthly','quarterly','semi_annual','annual')),
    responsible_party_ar  text,
    -- direction of improvement: higher is better, lower is better, or a band
    direction             text NOT NULL DEFAULT 'higher_better'
        CHECK (direction IN ('higher_better','lower_better','target_range')),
    target_value          numeric,
    acceptable_min        numeric,
    acceptable_max        numeric,
    multiplier            numeric NOT NULL DEFAULT 100,  -- e.g. 100 for %, 1000 for per-1000
    numerator_label_ar    text,
    denominator_label_ar  text,
    is_active             boolean NOT NULL DEFAULT true,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    deleted_at            timestamptz
);

-- ---------------------------------------------------------------------------
-- Which indicator is measured where
-- department_id NULL means the indicator is measured for the whole hospital.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indicator_assignments (
    id              uuid PRIMARY KEY,
    indicator_id    uuid NOT NULL REFERENCES indicators(id),
    hospital_id     uuid NOT NULL REFERENCES hospitals(id),
    department_id   uuid REFERENCES departments(id),
    target_override numeric,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_indicator_assignment
  ON indicator_assignments (
    indicator_id,
    hospital_id,
    COALESCE(department_id, '00000000-0000-0000-0000-000000000000'::uuid)
  )
  WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------------------
-- Reporting periods (one per hospital per period) with a review workflow
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reporting_periods (
    id            uuid PRIMARY KEY,
    hospital_id   uuid NOT NULL REFERENCES hospitals(id),
    period_type   text NOT NULL DEFAULT 'monthly'
        CHECK (period_type IN ('monthly','quarterly','annual')),
    year          integer NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month         integer CHECK (month BETWEEN 1 AND 12),
    quarter       integer CHECK (quarter BETWEEN 1 AND 4),
    status        text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','submitted','reviewed','approved','returned')),
    note          text,
    submitted_at  timestamptz,
    submitted_by  uuid,
    reviewed_at   timestamptz,
    reviewed_by   uuid,
    approved_at   timestamptz,
    approved_by   uuid,
    returned_at   timestamptz,
    returned_by   uuid,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_reporting_period
  ON reporting_periods (
    hospital_id,
    period_type,
    year,
    COALESCE(month, 0),
    COALESCE(quarter, 0)
  )
  WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------------------
-- Indicator values (the numbers entered or computed for a period)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indicator_values (
    id            uuid PRIMARY KEY,
    period_id     uuid NOT NULL REFERENCES reporting_periods(id),
    indicator_id  uuid NOT NULL REFERENCES indicators(id),
    department_id uuid REFERENCES departments(id),
    numerator     numeric,
    denominator   numeric,
    value         numeric,                    -- computed or directly entered
    value_type    text NOT NULL DEFAULT 'computed'
        CHECK (value_type IN ('computed','entered')),
    note          text,
    created_by    uuid,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_indicator_value
  ON indicator_values (
    period_id,
    indicator_id,
    COALESCE(department_id, '00000000-0000-0000-0000-000000000000'::uuid)
  )
  WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------------------
-- Revision history (full audit trail of value changes)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS indicator_value_revisions (
    id            uuid PRIMARY KEY,
    value_id      uuid NOT NULL REFERENCES indicator_values(id),
    action        text NOT NULL
        CHECK (action IN ('create','update','submit','review','approve','return','delete')),
    old_value     numeric,
    new_value     numeric,
    old_numerator numeric,
    new_numerator numeric,
    old_denominator numeric,
    new_denominator numeric,
    note          text,
    actor_user_id uuid,
    at            timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
ALTER TABLE indicator_assignments      ENABLE ROW LEVEL SECURITY;
ALTER TABLE indicator_assignments      FORCE ROW LEVEL SECURITY;
ALTER TABLE reporting_periods          ENABLE ROW LEVEL SECURITY;
ALTER TABLE reporting_periods          FORCE ROW LEVEL SECURITY;
ALTER TABLE indicator_values           ENABLE ROW LEVEL SECURITY;
ALTER TABLE indicator_values           FORCE ROW LEVEL SECURITY;
ALTER TABLE indicator_value_revisions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE indicator_value_revisions  FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS indicator_assignments_iso ON indicator_assignments;
CREATE POLICY indicator_assignments_iso ON indicator_assignments
  USING (app_can_see_hospital(hospital_id));

DROP POLICY IF EXISTS reporting_periods_iso ON reporting_periods;
CREATE POLICY reporting_periods_iso ON reporting_periods
  USING (app_can_see_hospital(hospital_id));

DROP POLICY IF EXISTS indicator_values_iso ON indicator_values;
CREATE POLICY indicator_values_iso ON indicator_values
  USING (
    period_id IN (
      SELECT p.id FROM reporting_periods p
      WHERE app_can_see_hospital(p.hospital_id)
    )
  );

DROP POLICY IF EXISTS indicator_value_revisions_iso ON indicator_value_revisions;
CREATE POLICY indicator_value_revisions_iso ON indicator_value_revisions
  USING (
    value_id IN (
      SELECT v.id FROM indicator_values v
      JOIN reporting_periods p ON p.id = v.period_id
      WHERE app_can_see_hospital(p.hospital_id)
    )
  );

CREATE INDEX IF NOT EXISTS idx_assignments_hospital   ON indicator_assignments(hospital_id);
CREATE INDEX IF NOT EXISTS idx_assignments_indicator  ON indicator_assignments(indicator_id);
CREATE INDEX IF NOT EXISTS idx_periods_hospital       ON reporting_periods(hospital_id, year, month);
CREATE INDEX IF NOT EXISTS idx_values_period          ON indicator_values(period_id);
CREATE INDEX IF NOT EXISTS idx_values_indicator       ON indicator_values(indicator_id);
CREATE INDEX IF NOT EXISTS idx_revisions_value        ON indicator_value_revisions(value_id, at);

-- ---------------------------------------------------------------------------
-- Permission to assign indicators to hospitals/departments
-- ---------------------------------------------------------------------------
INSERT INTO permissions (id, code, name_ar) VALUES
  ('01900000-0000-7001-8000-00000000000c', 'indicator.assign', 'إسناد المؤشرات للأقسام')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
  ('central_admin',   'indicator.assign'),
  ('hospital_manager', 'indicator.assign'),
  ('quality_manager', 'indicator.assign')
) AS m(role_code, perm_code)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = m.perm_code
ON CONFLICT DO NOTHING;
