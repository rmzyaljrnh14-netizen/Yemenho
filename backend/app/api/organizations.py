"""Organization, hospital and department endpoints (org.manage guarded)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_identity, require_permission
from app.db.base import get_db
from app.models.core import Department, Hospital, Organization
from app.schemas import (
    DepartmentCreate,
    DepartmentOut,
    HospitalCreate,
    HospitalOut,
    OrganizationCreate,
    OrganizationOut,
)
from app.services.identity import Identity, write_audit

router = APIRouter(tags=["organizations"])


# ---- Organizations ----
@router.get("/organizations", response_model=list[OrganizationOut])
def list_organizations(
    level: str | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[Organization]:
    stmt = select(Organization).where(Organization.deleted_at.is_(None))
    if level:
        stmt = stmt.where(Organization.level == level)
    return list(db.execute(stmt.order_by(Organization.name_ar)).scalars().all())


@router.post("/organizations", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    identity: Identity = Depends(require_permission("org.manage")),
    db: Session = Depends(get_db),
) -> Organization:
    org = Organization(
        name_ar=payload.name_ar, level=payload.level, parent_id=payload.parent_id, code=payload.code
    )
    db.add(org)
    db.flush()
    write_audit(
        db, entity_type="organization", entity_id=str(org.id), action="create",
        actor_user_id=identity.user.id, after={"name_ar": org.name_ar, "level": org.level},
    )
    db.commit()
    return org


# ---- Hospitals ----
@router.get("/hospitals", response_model=list[HospitalOut])
def list_hospitals(
    governorate_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[Hospital]:
    # RLS limits rows to the caller's scope automatically.
    stmt = select(Hospital).where(Hospital.deleted_at.is_(None))
    if governorate_id:
        stmt = stmt.where(Hospital.governorate_id == governorate_id)
    return list(db.execute(stmt.order_by(Hospital.name_ar)).scalars().all())


@router.post("/hospitals", response_model=HospitalOut, status_code=status.HTTP_201_CREATED)
def create_hospital(
    payload: HospitalCreate,
    identity: Identity = Depends(require_permission("org.manage")),
    db: Session = Depends(get_db),
) -> Hospital:
    exists = db.execute(select(Hospital).where(Hospital.code == payload.code)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "conflict", "message_ar": "رمز المستشفى مستخدم بالفعل."},
        )
    hosp = Hospital(
        name_ar=payload.name_ar,
        code=payload.code,
        governorate_id=payload.governorate_id,
        organization_id=payload.organization_id,
    )
    db.add(hosp)
    db.flush()
    write_audit(
        db, entity_type="hospital", entity_id=str(hosp.id), action="create",
        actor_user_id=identity.user.id, after={"name_ar": hosp.name_ar, "code": hosp.code},
        hospital_id=hosp.id,
    )
    db.commit()
    return hosp


@router.get("/hospitals/{hospital_id}", response_model=HospitalOut)
def get_hospital(
    hospital_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> Hospital:
    hosp = db.get(Hospital, hospital_id)
    if hosp is None or hosp.deleted_at is not None:
        # RLS hides out-of-scope rows, so this also covers "not allowed".
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المستشفى غير موجود."},
        )
    return hosp


# ---- Departments ----
@router.get("/hospitals/{hospital_id}/departments", response_model=list[DepartmentOut])
def list_departments(
    hospital_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[Department]:
    stmt = (
        select(Department)
        .where(Department.hospital_id == hospital_id, Department.deleted_at.is_(None))
        .order_by(Department.name_ar)
    )
    return list(db.execute(stmt).scalars().all())


@router.post(
    "/hospitals/{hospital_id}/departments",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    hospital_id: uuid.UUID,
    payload: DepartmentCreate,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> Department:
    if not identity.has("department.manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message_ar": "لا تملك صلاحية لإضافة قسم."},
        )
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
    dept = Department(
        hospital_id=hospital_id,
        name_ar=payload.name_ar,
        code=payload.code,
        manager_user_id=payload.manager_user_id,
    )
    db.add(dept)
    db.flush()
    write_audit(
        db, entity_type="department", entity_id=str(dept.id), action="create",
        actor_user_id=identity.user.id, after={"name_ar": dept.name_ar},
        hospital_id=hospital_id,
    )
    db.commit()
    return dept
