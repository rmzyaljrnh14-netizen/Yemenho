"""Request-scoped row-level-security context.

Sets app.is_central / app.hospital_id / app.governorate_id on the current
transaction so the RLS policies in 002_rls.sql can enforce isolation.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def apply_rls_context(
    db: Session,
    *,
    is_central: bool,
    hospital_id: str | None = None,
    governorate_id: str | None = None,
) -> None:
    db.execute(
        text("select set_config('app.is_central', :v, true)"),
        {"v": "true" if is_central else "false"},
    )
    db.execute(
        text("select set_config('app.hospital_id', :v, true)"),
        {"v": hospital_id or ""},
    )
    db.execute(
        text("select set_config('app.governorate_id', :v, true)"),
        {"v": governorate_id or ""},
    )


def clear_rls_context(db: Session) -> None:
    db.execute(text("reset app.is_central"))
    db.execute(text("reset app.hospital_id"))
    db.execute(text("reset app.governorate_id"))
