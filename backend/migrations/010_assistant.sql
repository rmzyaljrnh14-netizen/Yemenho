-- 010_assistant.sql — assistant permission (v0.8).
--
-- The assistant is read-only and only ever reads data the caller can already
-- see, so it is granted to the same roles that may view reports plus the
-- governorate officer. Idempotent: safe to re-run.

INSERT INTO permissions (id, code, name_ar) VALUES
  ('01900000-0000-7001-8000-00000000000d', 'assistant.use', 'استخدام المساعد الذكي')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM (VALUES
  ('central_admin',   'assistant.use'),
  ('gov_officer',     'assistant.use'),
  ('hospital_manager','assistant.use'),
  ('quality_manager', 'assistant.use'),
  ('auditor',         'assistant.use'),
  ('read_only',       'assistant.use')
) AS m(role_code, perm_code)
JOIN roles r ON r.code = m.role_code
JOIN permissions p ON p.code = m.perm_code
ON CONFLICT DO NOTHING;
