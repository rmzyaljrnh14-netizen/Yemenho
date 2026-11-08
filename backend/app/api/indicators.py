"""Indicator library and assignment endpoints (v0.4)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_identity, require_permission
from app.db.base import get_db
from app.models.core import Department, Hospital, Indicator, IndicatorAssignment
from app.schemas import (
    AssignedIndicatorOut,
    AssignmentUpsert,
    IndicatorAssignmentOut,
    IndicatorCreate,
    IndicatorOut,
    IndicatorUpdate,
)
from app.services.identity import Identity, now_utc, write_audit

router = APIRouter(tags=["indicators"])


# ---- Library ----
@router.get("/indicators", response_model=list[IndicatorOut])
def list_indicators(
    active_only: bool = Query(default=True),
    search: str | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[Indicator]:
    stmt = select(Indicator).where(Indicator.deleted_at.is_(None))
    if active_only:
        stmt = stmt.where(Indicator.is_active.is_(True))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Indicator.name_ar.ilike(like) | Indicator.code.ilike(like))
    return list(db.execute(stmt.order_by(Indicator.code)).scalars().all())


@router.get("/indicators/{indicator_id}", response_model=IndicatorOut)
def get_indicator(
    indicator_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> Indicator:
    ind = db.get(Indicator, indicator_id)
    if ind is None or ind.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المؤشر غير موجود."},
        )
    return ind


@router.post("/indicators", response_model=IndicatorOut, status_code=status.HTTP_201_CREATED)
def create_indicator(
    payload: IndicatorCreate,
    identity: Identity = Depends(require_permission("indicator.manage")),
    db: Session = Depends(get_db),
) -> Indicator:
    exists = db.execute(select(Indicator).where(Indicator.code == payload.code)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "conflict", "message_ar": "رمز المؤشر مستخدم بالفعل."},
        )
    ind = Indicator(**payload.model_dump())
    db.add(ind)
    db.flush()
    write_audit(
        db, entity_type="indicator", entity_id=str(ind.id), action="create",
        actor_user_id=identity.user.id, after={"code": ind.code, "name_ar": ind.name_ar},
    )
    db.commit()
    return ind


@router.patch("/indicators/{indicator_id}", response_model=IndicatorOut)
def update_indicator(
    indicator_id: uuid.UUID,
    payload: IndicatorUpdate,
    identity: Identity = Depends(require_permission("indicator.manage")),
    db: Session = Depends(get_db),
) -> Indicator:
    ind = db.get(Indicator, indicator_id)
    if ind is None or ind.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المؤشر غير موجود."},
        )
    before = {"name_ar": ind.name_ar, "target_value": ind.target_value, "direction": ind.direction}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ind, field, value)
    write_audit(
        db, entity_type="indicator", entity_id=str(ind.id), action="update",
        actor_user_id=identity.user.id, before=before,
        after={"name_ar": ind.name_ar, "target_value": ind.target_value, "direction": ind.direction},
    )
    db.commit()
    return ind


# ---- Assignments ----
@router.get("/hospitals/{hospital_id}/indicators", response_model=list[AssignedIndicatorOut])
def list_assigned_indicators(
    hospital_id: uuid.UUID,
    department_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[AssignedIndicatorOut]:
    hosp = db.get(Hospital, hospital_id)
    if hosp is None or hosp.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المستشفى غير موجود."},
        )
    stmt = (
        select(IndicatorAssignment, Indicator)
        .join(Indicator, Indicator.id == IndicatorAssignment.indicator_id)
        .where(
            IndicatorAssignment.hospital_id == hospital_id,
            IndicatorAssignment.deleted_at.is_(None),
            IndicatorAssignment.is_active.is_(True),
            Indicator.deleted_at.is_(None),
        )
    )
    if department_id is not None:
        stmt = stmt.where(IndicatorAssignment.department_id == department_id)
    rows = db.execute(stmt.order_by(Indicator.code)).all()
    return [
        AssignedIndicatorOut(
            assignment_id=a.id,
            indicator=IndicatorOut.model_validate(ind),
            department_id=a.department_id,
            target_override=a.target_override,
        )
        for a, ind in rows
    ]


@router.post(
    "/hospitals/{hospital_id}/indicators",
    response_model=IndicatorAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
def assign_indicator(
    hospital_id: uuid.UUID,
    payload: AssignmentUpsert,
    identity: Identity = Depends(require_permission("indicator.assign")),
    db: Session = Depends(get_db),
) -> IndicatorAssignment:
    if payload.hospital_id != hospital_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "validation_failed", "message_ar": "معرّف المستشفى غير متطابق."},
        )
    hosp = db.get(Hospital, hospital_id)
    if hosp is None or hosp.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المستشفى غير موجود."},
        )
    ind = db.get(Indicator, payload.indicator_id)
    if ind is None or ind.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المؤشر غير موجود."},
        )
    if payload.department_id is not None:
        dept = db.get(Department, payload.department_id)
        if dept is None or dept.hospital_id != hospital_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "validation_failed", "message_ar": "القسم لا يتبع هذا المستشفى."},
            )
    existing = db.execute(
        select(IndicatorAssignment).where(
            IndicatorAssignment.indicator_id == payload.indicator_id,
            IndicatorAssignment.hospital_id == hospital_id,
            IndicatorAssignment.department_id.is_(None)
            if payload.department_id is None
            else IndicatorAssignment.department_id == payload.department_id,
            IndicatorAssignment.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.target_override = payload.target_override
        existing.is_active = True
        write_audit(
            db, entity_type="indicator_assignment", entity_id=str(existing.id), action="update",
            actor_user_id=identity.user.id, hospital_id=hospital_id,
        )
        db.commit()
        return existing
    assignment = IndicatorAssignment(
        indicator_id=payload.indicator_id,
        hospital_id=hospital_id,
        department_id=payload.department_id,
        target_override=payload.target_override,
    )
    db.add(assignment)
    db.flush()
    write_audit(
        db, entity_type="indicator_assignment", entity_id=str(assignment.id), action="create",
        actor_user_id=identity.user.id,
        after={"indicator": ind.code, "hospital": str(hospital_id), "department": str(payload.department_id)},
        hospital_id=hospital_id,
    )
    db.commit()
    return assignment


@router.delete(
    "/hospitals/{hospital_id}/indicators/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unassign_indicator(
    hospital_id: uuid.UUID,
    assignment_id: uuid.UUID,
    identity: Identity = Depends(require_permission("indicator.assign")),
    db: Session = Depends(get_db),
) -> None:
    assignment = db.get(IndicatorAssignment, assignment_id)
    if (
        assignment is None
        or assignment.hospital_id != hospital_id
        or assignment.deleted_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "الإسناد غير موجود."},
        )
    assignment.deleted_at = now_utc()
    write_audit(
        db, entity_type="indicator_assignment", entity_id=str(assignment.id), action="delete",
        actor_user_id=identity.user.id, hospital_id=hospital_id,
    )
    db.commit()
