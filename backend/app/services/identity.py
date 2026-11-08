"""Identity, permissions and audit helpers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    AuditLog,
    Department,
    Hospital,
    Permission,
    Role,
    RolePermission,
    User,
    UserAssignment,
)


@dataclass
class Identity:
    user: User
    roles: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    is_central: bool = False
    hospital_id: uuid.UUID | None = None
    governorate_id: uuid.UUID | None = None
    scope_level: str = "none"

    def has(self, perm: str) -> bool:
        return perm in self.permissions


def load_identity(db: Session, user: User) -> Identity:
    """Resolve a user's roles, permissions and data scope."""
    assignments = db.execute(
        select(UserAssignment).where(
            UserAssignment.user_id == user.id,
            UserAssignment.deleted_at.is_(None),
        )
    ).scalars().all()

    roles: list[str] = []
    permissions: set[str] = set()
    is_central = False
    hospital_id: uuid.UUID | None = None
    governorate_id: uuid.UUID | None = None
    scope_level = "none"

    for a in assignments:
        role = db.get(Role, a.role_id)
        if role is None:
            continue
        roles.append(role.code)

        perm_rows = db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        ).fetchall()
        permissions.update(r[0] for r in perm_rows)

        if a.scope_type == "central":
            is_central = True
            scope_level = "central"
        elif a.scope_type == "governorate" and a.scope_id:
            # Only a governorate-scope assignment grants governorate visibility.
            # Hospital/department users must stay scoped to their hospital alone.
            governorate_id = a.scope_id
            if scope_level in ("none", "hospital"):
                scope_level = "governorate"
        elif a.scope_type == "hospital" and a.scope_id:
            if hospital_id is None:
                hospital_id = a.scope_id
            if scope_level == "none":
                scope_level = "hospital"
        elif a.scope_type == "department" and a.scope_id:
            dept = db.get(Department, a.scope_id)
            if dept is not None and hospital_id is None:
                hospital_id = dept.hospital_id
            if scope_level == "none":
                scope_level = "department"

    return Identity(
        user=user,
        roles=sorted(set(roles)),
        permissions=permissions,
        is_central=is_central,
        hospital_id=hospital_id,
        governorate_id=governorate_id,
        scope_level=scope_level,
    )


def write_audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    node: str | None = None,
    hospital_id: uuid.UUID | None = None,
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
            node=node,
            hospital_id=hospital_id,
            # Set the timestamp here rather than relying on the column default:
            # a server-side default forces an INSERT ... RETURNING, and the
            # read policy would then hide the fresh row from its own insert.
            at=now_utc(),
        )
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
