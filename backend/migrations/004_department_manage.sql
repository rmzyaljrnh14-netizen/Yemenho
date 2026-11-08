-- 004_department_manage.sql — separate permission for managing departments.
-- Hospital managers (and central admins) may manage departments; quality staff may not.

INSERT INTO permissions (id, code, name_ar) VALUES
  ('01900000-0000-7001-8000-00000000000b', 'department.manage', 'إدارة الأقسام')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
  ('central_admin', 'department.manage'),
  ('hospital_manager', 'department.manage')
) AS m(role_code, perm_code)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = m.perm_code
ON CONFLICT DO NOTHING;
