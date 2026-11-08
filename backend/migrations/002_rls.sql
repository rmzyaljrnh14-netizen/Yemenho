-- 002_rls.sql — row-level security for hospital/governorate data isolation.
-- The application sets per-transaction context via set_config(..., is_local=true):
--   app.is_central   'true' | 'false'
--   app.hospital_id  uuid text of the user's hospital (or '')
--   app.governorate_id uuid text of the user's governorate (or '')

CREATE OR REPLACE FUNCTION app_is_central() RETURNS boolean AS $$
  SELECT coalesce(current_setting('app.is_central', true), 'false') = 'true'
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION app_hospital_id() RETURNS text AS $$
  SELECT coalesce(current_setting('app.hospital_id', true), '')
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION app_governorate_id() RETURNS text AS $$
  SELECT coalesce(current_setting('app.governorate_id', true), '')
$$ LANGUAGE sql STABLE;

-- hospitals: central sees all; governorate sees its hospitals; hospital sees itself.
ALTER TABLE hospitals ENABLE ROW LEVEL SECURITY;
ALTER TABLE hospitals FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS hospitals_iso ON hospitals;
CREATE POLICY hospitals_iso ON hospitals
  USING (
    app_is_central()
    OR governorate_id::text = nullif(app_governorate_id(), '')
    OR id::text = nullif(app_hospital_id(), '')
  );

-- departments: central sees all; otherwise scoped to the user's hospital,
-- or to any hospital inside the user's governorate.
ALTER TABLE departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE departments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS departments_iso ON departments;
CREATE POLICY departments_iso ON departments
  USING (
    app_is_central()
    OR hospital_id::text = nullif(app_hospital_id(), '')
    OR hospital_id IN (
      SELECT h.id FROM hospitals h
      WHERE h.governorate_id::text = nullif(app_governorate_id(), '')
    )
  );
