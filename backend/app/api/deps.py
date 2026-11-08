"""FastAPI dependencies: current user, RLS context, permission guard."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import ACCESS, decode_token
from app.db.base import get_db
from app.db.context import apply_rls_context
from app.models.core import User
from app.services.identity import Identity, load_identity

_bearer = HTTPBearer(auto_error=False)


def _auth_error(code: str, message_ar: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message_ar": message_ar},
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Identity:
    if credentials is None or not credentials.credentials:
        raise _auth_error("unauthenticated", "المصادقة مطلوبة.")
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise _auth_error("token_expired", "انتهت صلاحية الجلسة، يرجى تسجيل الدخول من جديد.")
    if payload.get("type") != ACCESS:
        raise _auth_error("unauthenticated", "نوع الرمز غير صالح.")
    sub = payload.get("sub")
    if not sub:
        raise _auth_error("unauthenticated", "رمز غير صالح.")
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise _auth_error("unauthenticated", "رمز غير صالح.")

    user = db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise _auth_error("unauthenticated", "الحساب غير مفعّل.")

    identity = load_identity(db, user)
    apply_rls_context(
        db,
        is_central=identity.is_central,
        hospital_id=str(identity.hospital_id) if identity.hospital_id else None,
        governorate_id=str(identity.governorate_id) if identity.governorate_id else None,
    )
    return identity


def require_permission(permission: str):
    def _guard(identity: Identity = Depends(get_identity)) -> Identity:
        if not identity.has(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message_ar": "لا تملك صلاحية لهذا الإجراء."},
            )
        return identity

    return _guard
