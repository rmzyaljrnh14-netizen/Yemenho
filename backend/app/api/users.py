"""User, assignment and audit-log endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_identity, require_permission
from app.core.security import hash_password
from app.db.base import get_db
from app.models.core import Role, User, UserAssignment
from app.schemas import AssignmentCreate, AssignmentOut, UserCreate, UserOut
from app.services.identity import Identity, write_audit

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserOut])
def list_users(
    identity: Identity = Depends(require_permission("user.manage")),
    db: Session = Depends(get_db),
) -> list[User]:
    stmt = select(User).where(User.deleted_at.is_(None)).order_by(User.username)
    return list(db.execute(stmt).scalars().all())


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    identity: Identity = Depends(require_permission("user.manage")),
    db: Session = Depends(get_db),
) -> User:
    exists = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "conflict", "message_ar": "اسم المستخدم مستخدم بالفعل."},
        )
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    write_audit(
        db, entity_type="user", entity_id=str(user.id), action="create",
        actor_user_id=identity.user.id, after={"username": user.username},
    )
    db.commit()
    return user


@router.post("/users/assignments", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    identity: Identity = Depends(require_permission("user.manage")),
    db: Session = Depends(get_db),
) -> UserAssignment:
    role = db.execute(select(Role).where(Role.code == payload.role_code)).scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "validation_failed", "message_ar": "الدور غير معروف."},
        )
    user = db.get(User, payload.user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المستخدم غير موجود."},
        )
    assignment = UserAssignment(
        user_id=payload.user_id,
        role_id=role.id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
    )
    db.add(assignment)
    db.flush()
    write_audit(
        db, entity_type="user_assignment", entity_id=str(assignment.id), action="create",
        actor_user_id=identity.user.id,
        after={"user_id": str(payload.user_id), "role": payload.role_code, "scope": payload.scope_type},
    )
    db.commit()
    return assignment
