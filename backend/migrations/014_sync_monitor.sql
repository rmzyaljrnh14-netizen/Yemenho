-- 014_sync_monitor.sql — permissions for the national sync monitor (v0.12).
-- Idempotent: safe to re-run.
--
-- Reading the sync picture (device health, open conflicts) needs ``sync.view``;
-- acting on a conflict (review / dismiss) needs ``sync.manage``. The sync tables
-- already carry row-level security from 007_sync.sql, so a hospital user only
-- ever sees their own device and conflicts; central sees everything.

INSERT INTO permissions (id, code, name_ar) VALUES
  ('01900000-0000-7001-8000-000000000010', 'sync.view',   'متابعة المزامنة والأجهزة'),
  ('01900000-0000-7001-8000-000000000011', 'sync.manage', 'معالجة تعارضات المزامنة')
ON CONFLICT (code) DO NOTHING;

-- role -> permission matrix (national, governorate, hospital quality/management).
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
  ('central_admin',    'sync.view'),
  ('central_admin',    'sync.manage'),
  ('gov_officer',      'sync.view'),
  ('hospital_manager', 'sync.view'),
  ('hospital_manager', 'sync.manage'),
  ('quality_manager',  'sync.view'),
  ('quality_manager',  'sync.manage'),
  ('indicator_officer','sync.view'),
  ('auditor',          'sync.view')
) AS m(role_code, perm_code)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = m.perm_code
ON CONFLICT DO NOTHING;
