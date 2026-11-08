-- 003_seed_reference.sql — reference data: roles and permissions.
-- Idempotent: safe to re-run.

INSERT INTO roles (id, code, name_ar) VALUES
  ('01900000-0000-7000-8000-000000000001', 'central_admin',  'مدير النظام المركزي'),
  ('01900000-0000-7000-8000-000000000002', 'gov_officer',    'مسؤول المحافظة'),
  ('01900000-0000-7000-8000-000000000003', 'hospital_manager','مدير المستشفى'),
  ('01900000-0000-7000-8000-000000000004', 'quality_manager','مدير الجودة'),
  ('01900000-0000-7000-8000-000000000005', 'indicator_officer','مسؤول المؤشرات'),
  ('01900000-0000-7000-8000-000000000006', 'department_officer','مسؤول القسم'),
  ('01900000-0000-7000-8000-000000000007', 'auditor',        'المدقق'),
  ('01900000-0000-7000-8000-000000000008', 'read_only',      'قراءة فقط')
ON CONFLICT (code) DO NOTHING;

INSERT INTO permissions (id, code, name_ar) VALUES
  ('01900000-0000-7001-8000-000000000001', 'org.manage',       'إدارة المؤسسات'),
  ('01900000-0000-7001-8000-000000000002', 'user.manage',      'إدارة المستخدمين'),
  ('01900000-0000-7001-8000-000000000003', 'indicator.manage', 'إدارة مكتبة المؤشرات'),
  ('01900000-0000-7001-8000-000000000004', 'indicator.enter',  'إدخال بيانات المؤشرات'),
  ('01900000-0000-7001-8000-000000000005', 'period.submit',    'إرسال للمراجعة'),
  ('01900000-0000-7001-8000-000000000006', 'period.review',    'مراجعة'),
  ('01900000-0000-7001-8000-000000000007', 'period.approve',   'اعتماد'),
  ('01900000-0000-7001-8000-000000000008', 'quality.manage',   'إدارة الجودة وسلامة المرضى'),
  ('01900000-0000-7001-8000-000000000009', 'report.view',      'عرض التقارير'),
  ('01900000-0000-7001-8000-00000000000a', 'audit.view',       'عرض سجل التدقيق')
ON CONFLICT (code) DO NOTHING;

-- role -> permission matrix
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
  ('central_admin',   'org.manage'),
  ('central_admin',   'user.manage'),
  ('central_admin',   'indicator.manage'),
  ('central_admin',   'indicator.enter'),
  ('central_admin',   'period.submit'),
  ('central_admin',   'period.review'),
  ('central_admin',   'period.approve'),
  ('central_admin',   'quality.manage'),
  ('central_admin',   'report.view'),
  ('central_admin',   'audit.view'),
  ('gov_officer',     'period.review'),
  ('gov_officer',     'period.approve'),
  ('gov_officer',     'report.view'),
  ('gov_officer',     'audit.view'),
  ('hospital_manager', 'user.manage'),
  ('hospital_manager', 'period.review'),
  ('hospital_manager', 'period.approve'),
  ('hospital_manager', 'quality.manage'),
  ('hospital_manager', 'report.view'),
  ('hospital_manager', 'audit.view'),
  ('quality_manager', 'indicator.enter'),
  ('quality_manager', 'period.submit'),
  ('quality_manager', 'period.review'),
  ('quality_manager', 'period.approve'),
  ('quality_manager', 'quality.manage'),
  ('quality_manager', 'report.view'),
  ('quality_manager', 'audit.view'),
  ('indicator_officer', 'indicator.enter'),
  ('indicator_officer', 'period.submit'),
  ('indicator_officer', 'report.view'),
  ('department_officer', 'indicator.enter'),
  ('department_officer', 'period.submit'),
  ('department_officer', 'report.view'),
  ('auditor',         'period.review'),
  ('auditor',         'report.view'),
  ('auditor',         'audit.view'),
  ('read_only',       'report.view')
) AS m(role_code, perm_code)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = m.perm_code
ON CONFLICT DO NOTHING;
