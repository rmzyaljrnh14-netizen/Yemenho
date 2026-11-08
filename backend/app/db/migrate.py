"""Run SQL migrations in filename order, tracking applied versions.

Migrations run as the admin (superuser) role. They also create the non-superuser
application role and grant it table privileges, so the running app cannot bypass
row-level security.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import AdminSessionLocal

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def _ensure_registry(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now(),
                description text
            )
            """
        )
    )
    db.commit()


def _ensure_app_role(db: Session) -> None:
    """Create the least-privilege application role if missing.

    NOSUPERUSER + NOBYPASSRLS are essential: a superuser bypasses RLS even with
    FORCE ROW LEVEL SECURITY.
    """
    settings = get_settings()
    role = settings.app_db_role
    password = settings.app_db_password
    exists = db.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).fetchone()
    if not exists:
        db.execute(text(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\' NOSUPERUSER NOBYPASSRLS'))
    else:
        db.execute(text(f'ALTER ROLE "{role}" LOGIN PASSWORD \'{password}\' NOSUPERUSER NOBYPASSRLS'))
    db.commit()


def _grant_privileges(db: Session) -> None:
    """Grant the app role access to the current schema and tables.

    Called after each migration batch because new tables need grants too.
    """
    settings = get_settings()
    role = settings.app_db_role
    db.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
    db.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'))
    db.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
    db.execute(
        text(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"'
        )
    )
    db.execute(
        text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "{role}"')
    )
    db.commit()


def applied_versions(db: Session) -> set[str]:
    rows = db.execute(text("SELECT version FROM schema_migrations")).fetchall()
    return {r[0] for r in rows}


def run_migrations() -> list[str]:
    applied: list[str] = []
    db = AdminSessionLocal()
    try:
        _ensure_registry(db)
        _ensure_app_role(db)
        done = applied_versions(db)
        db.commit()
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            if version in done:
                continue
            sql = path.read_text(encoding="utf-8")
            db.execute(text(sql))
            db.execute(
                text("INSERT INTO schema_migrations (version, description) VALUES (:v, :d)"),
                {"v": version, "d": path.stem},
            )
            db.commit()
            applied.append(version)
        # Keep the app role's grants current (new tables from this run).
        _grant_privileges(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return applied


if __name__ == "__main__":
    result = run_migrations()
    print("applied:", result or "nothing new")

