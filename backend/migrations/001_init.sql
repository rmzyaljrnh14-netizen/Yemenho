-- 001_init.sql — core schema for v0.1
-- Organizations (central -> governorate -> district -> hospital), hospitals,
-- departments, identity (users/roles/permissions/assignments), audit log.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    description text
);

CREATE TABLE IF NOT EXISTS organizations (
    id         uuid PRIMARY KEY,
    parent_id  uuid REFERENCES organizations(id),
    level      text NOT NULL CHECK (level IN ('central', 'governorate', 'district', 'hospital')),
    name_ar    text NOT NULL,
    code       text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS hospitals (
    id              uuid PRIMARY KEY,
    organization_id uuid REFERENCES organizations(id),
    governorate_id  uuid REFERENCES organizations(id),
    name_ar         text NOT NULL,
    code            text UNIQUE NOT NULL,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz
);

CREATE TABLE IF NOT EXISTS departments (
    id              uuid PRIMARY KEY,
    hospital_id     uuid NOT NULL REFERENCES hospitals(id),
    name_ar         text NOT NULL,
    code            text,
    manager_user_id uuid,
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz
);

CREATE TABLE IF NOT EXISTS roles (
    id      uuid PRIMARY KEY,
    code    text UNIQUE NOT NULL,
    name_ar text NOT NULL
);

CREATE TABLE IF NOT EXISTS permissions (
    id      uuid PRIMARY KEY,
    code    text UNIQUE NOT NULL,
    name_ar text NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       uuid NOT NULL REFERENCES roles(id),
    permission_id uuid NOT NULL REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS users (
    id            uuid PRIMARY KEY,
    username      text UNIQUE NOT NULL,
    display_name  text NOT NULL,
    email         text,
    password_hash text NOT NULL,
    is_active     boolean NOT NULL DEFAULT true,
    failed_logins integer NOT NULL DEFAULT 0,
    locked_until  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz
);

CREATE TABLE IF NOT EXISTS user_assignments (
    id         uuid PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users(id),
    scope_type text NOT NULL CHECK (scope_type IN ('central', 'governorate', 'hospital', 'department')),
    scope_id   uuid,
    role_id    uuid NOT NULL REFERENCES roles(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            uuid PRIMARY KEY,
    entity_type   text NOT NULL,
    entity_id     text NOT NULL,
    action        text NOT NULL,
    actor_user_id uuid,
    before_json   jsonb,
    after_json    jsonb,
    at            timestamptz NOT NULL DEFAULT now(),
    node          text
);

CREATE INDEX IF NOT EXISTS idx_departments_hospital ON departments(hospital_id);
CREATE INDEX IF NOT EXISTS idx_hospitals_gov        ON hospitals(governorate_id);
CREATE INDEX IF NOT EXISTS idx_assignments_user     ON user_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity         ON audit_log(entity_type, entity_id, at);
