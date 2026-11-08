"""Authentication endpoints."""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_identity
from app.core.config import get_settings
from app.core.security import ACCESS, REFRESH, create_token, decode_token, verify_password
from app.db.base import get_db
from app.db.context import apply_rls_context
from app.models.core import User
from app.schemas import LoginRequest, MeResponse, RefreshRequest, ScopeOrg, TokenResponse
from app.services.identity import Identity, load_identity, now_utc, write_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    settings = get_settings()
    user = db.execute(
        select(User).where(User.username == payload.username, User.deleted_at.is_(None))
    ).scalar_one_or_none()

    generic = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthenticated", "message_ar": "اسم المستخدم أو كلمة المرور غير صحيحة."},
    )

    if user is None:
        write_audit(db, entity_type="auth", entity_id=payload.username, action="login_failed")
        db.commit()
        raise generic

    if user.locked_until is not None and user.locked_until > now_utc():
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"code": "account_locked", "message_ar": "الحساب مقفل مؤقتاً. حاول لاحقاً."},
        )

    if not user.is_active:
        raise generic

    if not verify_password(payload.password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now_utc() + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
        write_audit(
            db, entity_type="auth", entity_id=str(user.id), action="login_failed",
            actor_user_id=user.id, node=payload.client_node,
        )
        db.commit()
        raise generic

    user.failed_logins = 0
    user.locked_until = None
    write_audit(
        db, entity_type="auth", entity_id=str(user.id), action="login_success",
        actor_user_id=user.id, node=payload.client_node,
    )
    db.commit()

    return TokenResponse(
        access_token=create_token(str(user.id), ACCESS, {"username": user.username}),
        refresh_token=create_token(str(user.id), REFRESH),
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    settings = get_settings()
    try:
        data = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "token_expired", "message_ar": "الجلسة منتهية."},
        )
    if data.get("type") != REFRESH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthenticated", "message_ar": "نوع الرمز غير صالح."},
        )
    user = db.get(User, uuid.UUID(data["sub"]))
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthenticated", "message_ar": "الحساب غير مفعّل."},
        )
    return TokenResponse(
        access_token=create_token(str(user.id), ACCESS, {"username": user.username}),
        refresh_token=create_token(str(user.id), REFRESH),
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/logout")
def logout(identity: Identity = Depends(get_identity), db: Session = Depends(get_db)) -> dict:
    write_audit(
        db, entity_type="auth", entity_id=str(identity.user.id), action="logout",
        actor_user_id=identity.user.id,
    )
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(identity: Identity = Depends(get_identity)) -> MeResponse:
    return MeResponse(
        id=identity.user.id,
        username=identity.user.username,
        display_name=identity.user.display_name,
        is_active=identity.user.is_active,
        roles=identity.roles,
        scopes=sorted(identity.permissions),
        scope_org=ScopeOrg(
            level=identity.scope_level,
            hospital_id=identity.hospital_id,
            governorate_id=identity.governorate_id,
        ),
    )
