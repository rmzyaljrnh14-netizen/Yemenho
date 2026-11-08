"""Engine and session factory.

Two engines:
  * engine      — the application role (non-superuser). Row-level security applies.
  * admin_engine — a superuser used only by migrations and seeding (bypasses RLS).
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    future=True,
)

admin_engine = create_engine(
    _settings.admin_database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
AdminSessionLocal = sessionmaker(bind=admin_engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """Yield a session for the duration of a request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
