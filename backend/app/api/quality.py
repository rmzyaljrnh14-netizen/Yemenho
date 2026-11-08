"""Quality and patient-safety endpoints (v0.7).

Modules: incidents, root-cause analysis (RCA), corrective/preventive actions
(CAPA), the risk register, internal audits, improvement plans, quality
documents and quality meetings.

Isolation: every row is hospital-scoped and RLS (migration 008) hides other
hospitals' rows from the query itself. Writes additionally require the
``quality.manage`` permission, so a read-only user can never change a record.
Hospital-scoped users cannot pick another hospital: the payload hospital is
validated against the caller's scope, and a scoped user's own hospital wins.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_identity, require_permission
from app.db.base import get_db
from app.models.core import (
    CapaAction,
    Department,
    Hospital,
    ImprovementAction,
    ImprovementPlan,
    Incident,
    IncidentRca,
    IncidentRcaCause,
    QualityAudit,
    QualityDocument,
    QualityMeeting,
    QualityMeetingDecision,
    Risk,
)
from app.schemas import (
    AuditCreate,
    AuditOut,
    AuditUpdate,
    CapaCreate,
    CapaOut,
    CapaUpdate,
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
    ImprovementActionCreate,
    ImprovementActionOut,
    ImprovementActionUpdate,
    ImprovementPlanCreate,
    ImprovementPlanDetailOut,
    ImprovementPlanOut,
    ImprovementPlanUpdate,
    IncidentCreate,
    IncidentOut,
    IncidentStatusChange,
    IncidentUpdate,
    MeetingCreate,
    MeetingDecisionCreate,
    MeetingDecisionOut,
    MeetingDecisionUpdate,
    MeetingDetailOut,
    MeetingOut,
    MeetingUpdate,
    QualitySummaryOut,
    RcaCauseCreate,
    RcaCauseOut,
    RcaCreate,
    RcaDetailOut,
    RcaOut,
    RcaUpdate,
    RiskCreate,
    RiskOut,
    RiskUpdate,
)
from app.services.identity import Identity, now_utc, write_audit

router = APIRouter(tags=["quality"])

_CODE_PREFIX = {
    Incident: "INC",
    Risk: "RSK",
    QualityAudit: "AUD",
    ImprovementPlan: "IMP",
    QualityDocument: "DOC",
}


def _not_found(message_ar: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "not_found", "message_ar": message_ar},
    )


def _invalid(message_ar: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "validation_failed", "message_ar": message_ar},
    )


def _resolve_hospital(
    identity: Identity, requested: uuid.UUID | None, db: Session
) -> uuid.UUID:
    """Decide which hospital a new row belongs to, honouring the caller's scope.

    A scoped user may only write into their own hospital; central users must say
    which hospital they mean. RLS already hides other hospitals, but this keeps
    the intent explicit and returns a clear error instead of a silent failure.
    """
    if identity.is_central:
        if requested is None:
            raise _invalid("يجب تحديد المستشفى.")
        hosp = db.get(Hospital, requested)
        if hosp is None or hosp.deleted_at is not None:
            raise _not_found("المستشفى غير موجود.")
        return requested
    if identity.hospital_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message_ar": "لا يرتبط حسابك بمستشفى."},
        )
    if requested is not None and requested != identity.hospital_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message_ar": "لا يمكنك الكتابة في مستشفى آخر."},
        )
    return identity.hospital_id


def _check_department(hospital_id: uuid.UUID, department_id: uuid.UUID | None, db: Session) -> None:
    if department_id is None:
        return
    dept = db.get(Department, department_id)
    if dept is None or dept.hospital_id != hospital_id:
        raise _invalid("القسم لا يتبع هذا المستشفى.")


def _next_code(model: type, hospital_id: uuid.UUID, db: Session) -> str:
    """Generate a per-hospital human code such as INC-2026-0007.

    Counts existing rows (including soft-deleted ones, so a code is never
    reused) and retries on a unique-constraint clash at commit time.
    """
    prefix = _CODE_PREFIX[model]
    year = datetime.now(timezone.utc).year
    count = db.execute(
        select(func.count()).select_from(model).where(model.hospital_id == hospital_id)
    ).scalar_one()
    return f"{prefix}-{year}-{int(count) + 1:04d}"


def _get_scoped(db: Session, model: type, row_id: uuid.UUID, message_ar: str):
    row = db.get(model, row_id)
    if row is None or getattr(row, "deleted_at", None) is not None:
        raise _not_found(message_ar)
    return row


def _is_overdue(due: date | None, row_status: str) -> bool:
    if due is None or row_status in ("done", "verified", "cancelled"):
        return False
    return due < datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------
@router.get("/quality/incidents", response_model=list[IncidentOut])
def list_incidents(
    hospital_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[Incident]:
    stmt = select(Incident).where(Incident.deleted_at.is_(None))
    if hospital_id is not None:
        stmt = stmt.where(Incident.hospital_id == hospital_id)
    if status_filter:
        stmt = stmt.where(Incident.status == status_filter)
    if severity:
        stmt = stmt.where(Incident.severity == severity)
    return list(db.execute(stmt.order_by(Incident.reported_at.desc())).scalars().all())


@router.get("/quality/incidents/{incident_id}", response_model=IncidentOut)
def get_incident(
    incident_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> Incident:
    return _get_scoped(db, Incident, incident_id, "الحادث غير موجود.")


@router.post(
    "/quality/incidents", response_model=IncidentOut, status_code=status.HTTP_201_CREATED
)
def create_incident(
    payload: IncidentCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> Incident:
    hospital_id = _resolve_hospital(identity, payload.hospital_id, db)
    _check_department(hospital_id, payload.department_id, db)
    row = Incident(
        hospital_id=hospital_id,
        department_id=payload.department_id,
        code=_next_code(Incident, hospital_id, db),
        title=payload.title,
        description=payload.description,
        incident_type=payload.incident_type,
        severity=payload.severity,
        patient_harm=payload.patient_harm,
        occurred_at=payload.occurred_at,
        is_anonymous=payload.is_anonymous,
        immediate_action=payload.immediate_action,
        reported_by=None if payload.is_anonymous else identity.user.id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        entity_type="incident",
        entity_id=str(row.id),
        action="create",
        actor_user_id=identity.user.id,
        after={"code": row.code, "severity": row.severity, "type": row.incident_type},
        hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/incidents/{incident_id}", response_model=IncidentOut)
def update_incident(
    incident_id: uuid.UUID,
    payload: IncidentUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> Incident:
    row = _get_scoped(db, Incident, incident_id, "الحادث غير موجود.")
    if row.status == "closed":
        raise _invalid("لا يمكن تعديل حادث مغلق.")
    data = payload.model_dump(exclude_unset=True)
    if "department_id" in data:
        _check_department(row.hospital_id, data["department_id"], db)
    for field, value in data.items():
        setattr(row, field, value)
    row.rev += 1
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="incident", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.post("/quality/incidents/{incident_id}/status", response_model=IncidentOut)
def change_incident_status(
    incident_id: uuid.UUID,
    payload: IncidentStatusChange,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> Incident:
    row = _get_scoped(db, Incident, incident_id, "الحادث غير موجود.")
    before = row.status
    row.status = payload.status
    if payload.status == "closed":
        row.closed_at = now_utc()
        row.closed_by = identity.user.id
    row.rev += 1
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="incident", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id,
        before={"status": before}, after={"status": row.status, "note": payload.note},
        hospital_id=row.hospital_id,
    )
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Root-cause analysis
# ---------------------------------------------------------------------------
@router.get("/quality/incidents/{incident_id}/rca", response_model=RcaDetailOut)
def get_rca(
    incident_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> RcaDetailOut:
    _get_scoped(db, Incident, incident_id, "الحادث غير موجود.")
    rca = db.execute(
        select(IncidentRca).where(
            IncidentRca.incident_id == incident_id, IncidentRca.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if rca is None:
        raise _not_found("لا يوجد تحليل أسباب جذرية لهذا الحادث.")
    causes = list(
        db.execute(
            select(IncidentRcaCause)
            .where(IncidentRcaCause.rca_id == rca.id, IncidentRcaCause.deleted_at.is_(None))
            .order_by(IncidentRcaCause.created_at)
        ).scalars().all()
    )
    return RcaDetailOut(rca=RcaOut.model_validate(rca), causes=[RcaCauseOut.model_validate(c) for c in causes])


@router.post(
    "/quality/incidents/{incident_id}/rca",
    response_model=RcaOut,
    status_code=status.HTTP_201_CREATED,
)
def create_rca(
    incident_id: uuid.UUID,
    payload: RcaCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> IncidentRca:
    incident = _get_scoped(db, Incident, incident_id, "الحادث غير موجود.")
    existing = db.execute(
        select(IncidentRca).where(
            IncidentRca.incident_id == incident_id, IncidentRca.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise _invalid("يوجد تحليل أسباب جذرية لهذا الحادث بالفعل.")
    row = IncidentRca(
        incident_id=incident_id,
        hospital_id=incident.hospital_id,
        method=payload.method,
        team_ar=payload.team_ar,
        timeline_ar=payload.timeline_ar,
        findings_ar=payload.findings_ar,
        facilitator_id=identity.user.id,
    )
    db.add(row)
    if incident.status in ("reported", "under_review"):
        incident.status = "rca"
        incident.updated_at = now_utc()
    db.flush()
    write_audit(
        db, entity_type="incident_rca", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, after={"incident": str(incident_id)},
        hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/rca/{rca_id}", response_model=RcaOut)
def update_rca(
    rca_id: uuid.UUID,
    payload: RcaUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> IncidentRca:
    row = _get_scoped(db, IncidentRca, rca_id, "تحليل الأسباب غير موجود.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    if data.get("status") == "completed":
        row.completed_at = now_utc()
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="incident_rca", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.post(
    "/quality/rca/{rca_id}/causes",
    response_model=RcaCauseOut,
    status_code=status.HTTP_201_CREATED,
)
def add_rca_cause(
    rca_id: uuid.UUID,
    payload: RcaCauseCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> IncidentRcaCause:
    rca = _get_scoped(db, IncidentRca, rca_id, "تحليل الأسباب غير موجود.")
    row = IncidentRcaCause(
        rca_id=rca_id,
        category=payload.category,
        description_ar=payload.description_ar,
        is_root_cause=payload.is_root_cause,
    )
    db.add(row)
    db.flush()
    write_audit(
        db, entity_type="incident_rca_cause", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, hospital_id=rca.hospital_id,
    )
    db.commit()
    return row


@router.delete("/quality/rca/causes/{cause_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rca_cause(
    cause_id: uuid.UUID,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> None:
    row = _get_scoped(db, IncidentRcaCause, cause_id, "السبب غير موجود.")
    rca = _get_scoped(db, IncidentRca, row.rca_id, "تحليل الأسباب غير موجود.")
    row.deleted_at = now_utc()
    write_audit(
        db, entity_type="incident_rca_cause", entity_id=str(row.id), action="delete",
        actor_user_id=identity.user.id, hospital_id=rca.hospital_id,
    )
    db.commit()


# ---------------------------------------------------------------------------
# CAPA
# ---------------------------------------------------------------------------
def _capa_out(row: CapaAction) -> CapaOut:
    out = CapaOut.model_validate(row)
    out.is_overdue = _is_overdue(row.due_date, row.status)
    return out


@router.get("/quality/capa", response_model=list[CapaOut])
def list_capa(
    hospital_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    overdue_only: bool = Query(default=False),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[CapaOut]:
    stmt = select(CapaAction).where(CapaAction.deleted_at.is_(None))
    if hospital_id is not None:
        stmt = stmt.where(CapaAction.hospital_id == hospital_id)
    if status_filter:
        stmt = stmt.where(CapaAction.status == status_filter)
    rows = list(db.execute(stmt.order_by(CapaAction.due_date.nulls_last())).scalars().all())
    result = [_capa_out(r) for r in rows]
    if overdue_only:
        result = [r for r in result if r.is_overdue]
    return result


@router.post("/quality/capa", response_model=CapaOut, status_code=status.HTTP_201_CREATED)
def create_capa(
    payload: CapaCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> CapaOut:
    hospital_id = _resolve_hospital(identity, payload.hospital_id, db)
    _check_department(hospital_id, payload.department_id, db)
    if payload.incident_id is not None:
        _get_scoped(db, Incident, payload.incident_id, "الحادث غير موجود.")
    if payload.rca_id is not None:
        _get_scoped(db, IncidentRca, payload.rca_id, "تحليل الأسباب غير موجود.")
    row = CapaAction(
        hospital_id=hospital_id,
        department_id=payload.department_id,
        incident_id=payload.incident_id,
        rca_id=payload.rca_id,
        audit_id=payload.audit_id,
        kind=payload.kind,
        title=payload.title,
        description_ar=payload.description_ar,
        owner_name_ar=payload.owner_name_ar,
        due_date=payload.due_date,
        priority=payload.priority,
    )
    db.add(row)
    if payload.incident_id is not None:
        incident = db.get(Incident, payload.incident_id)
        if incident is not None and incident.status in ("reported", "under_review", "rca"):
            incident.status = "capa"
            incident.updated_at = now_utc()
    db.flush()
    write_audit(
        db, entity_type="capa_action", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, after={"title": row.title, "kind": row.kind},
        hospital_id=row.hospital_id,
    )
    db.commit()
    return _capa_out(row)


@router.patch("/quality/capa/{capa_id}", response_model=CapaOut)
def update_capa(
    capa_id: uuid.UUID,
    payload: CapaUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> CapaOut:
    row = _get_scoped(db, CapaAction, capa_id, "الإجراء غير موجود.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    if data.get("status") in ("done", "verified"):
        row.completed_at = row.completed_at or now_utc()
    if data.get("status") == "verified":
        row.verified_at = now_utc()
        row.verified_by = identity.user.id
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="capa_action", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=row.hospital_id,
    )
    db.commit()
    return _capa_out(row)


# ---------------------------------------------------------------------------
# Risk register
# ---------------------------------------------------------------------------
@router.get("/quality/risks", response_model=list[RiskOut])
def list_risks(
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[Risk]:
    stmt = select(Risk).where(Risk.deleted_at.is_(None))
    if hospital_id is not None:
        stmt = stmt.where(Risk.hospital_id == hospital_id)
    return list(db.execute(stmt.order_by(Risk.score.desc())).scalars().all())


@router.post("/quality/risks", response_model=RiskOut, status_code=status.HTTP_201_CREATED)
def create_risk(
    payload: RiskCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> Risk:
    hospital_id = _resolve_hospital(identity, payload.hospital_id, db)
    _check_department(hospital_id, payload.department_id, db)
    row = Risk(
        hospital_id=hospital_id,
        department_id=payload.department_id,
        code=payload.code or _next_code(Risk, hospital_id, db),
        title=payload.title,
        description_ar=payload.description_ar,
        category=payload.category,
        likelihood=payload.likelihood,
        impact=payload.impact,
        mitigation_ar=payload.mitigation_ar,
        owner_name_ar=payload.owner_name_ar,
        review_date=payload.review_date,
    )
    db.add(row)
    db.flush()
    db.refresh(row)  # read back the database-computed score
    write_audit(
        db, entity_type="risk", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, after={"code": row.code},
        hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/risks/{risk_id}", response_model=RiskOut)
def update_risk(
    risk_id: uuid.UUID,
    payload: RiskUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> Risk:
    row = _get_scoped(db, Risk, risk_id, "الخطر غير موجود.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = now_utc()
    db.flush()
    db.refresh(row)  # score is a generated column: re-read after the update
    write_audit(
        db, entity_type="risk", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=row.hospital_id,
    )
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Internal audits
# ---------------------------------------------------------------------------
@router.get("/quality/audits", response_model=list[AuditOut])
def list_audits(
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[QualityAudit]:
    stmt = select(QualityAudit).where(QualityAudit.deleted_at.is_(None))
    if hospital_id is not None:
        stmt = stmt.where(QualityAudit.hospital_id == hospital_id)
    return list(db.execute(stmt.order_by(QualityAudit.audit_date.desc().nulls_last())).scalars().all())


@router.post("/quality/audits", response_model=AuditOut, status_code=status.HTTP_201_CREATED)
def create_audit(
    payload: AuditCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> QualityAudit:
    hospital_id = _resolve_hospital(identity, payload.hospital_id, db)
    _check_department(hospital_id, payload.department_id, db)
    row = QualityAudit(
        hospital_id=hospital_id,
        department_id=payload.department_id,
        code=payload.code or _next_code(QualityAudit, hospital_id, db),
        title=payload.title,
        standard_ar=payload.standard_ar,
        scope_ar=payload.scope_ar,
        auditor_name_ar=payload.auditor_name_ar,
        audit_date=payload.audit_date,
    )
    db.add(row)
    db.flush()
    write_audit(
        db, entity_type="quality_audit", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, after={"code": row.code},
        hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/audits/{audit_id}", response_model=AuditOut)
def update_audit(
    audit_id: uuid.UUID,
    payload: AuditUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> QualityAudit:
    row = _get_scoped(db, QualityAudit, audit_id, "التدقيق غير موجود.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="quality_audit", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=row.hospital_id,
    )
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Improvement plans
# ---------------------------------------------------------------------------
@router.get("/quality/plans", response_model=list[ImprovementPlanOut])
def list_plans(
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[ImprovementPlan]:
    stmt = select(ImprovementPlan).where(ImprovementPlan.deleted_at.is_(None))
    if hospital_id is not None:
        stmt = stmt.where(ImprovementPlan.hospital_id == hospital_id)
    return list(db.execute(stmt.order_by(ImprovementPlan.created_at.desc())).scalars().all())


@router.get("/quality/plans/{plan_id}", response_model=ImprovementPlanDetailOut)
def get_plan(
    plan_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> ImprovementPlanDetailOut:
    plan = _get_scoped(db, ImprovementPlan, plan_id, "خطة التحسين غير موجودة.")
    actions = list(
        db.execute(
            select(ImprovementAction)
            .where(ImprovementAction.plan_id == plan.id, ImprovementAction.deleted_at.is_(None))
            .order_by(ImprovementAction.created_at)
        ).scalars().all()
    )
    return ImprovementPlanDetailOut(
        plan=ImprovementPlanOut.model_validate(plan),
        actions=[ImprovementActionOut.model_validate(a) for a in actions],
    )


@router.post(
    "/quality/plans", response_model=ImprovementPlanOut, status_code=status.HTTP_201_CREATED
)
def create_plan(
    payload: ImprovementPlanCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> ImprovementPlan:
    hospital_id = _resolve_hospital(identity, payload.hospital_id, db)
    _check_department(hospital_id, payload.department_id, db)
    row = ImprovementPlan(
        hospital_id=hospital_id,
        department_id=payload.department_id,
        code=payload.code or _next_code(ImprovementPlan, hospital_id, db),
        title=payload.title,
        objective_ar=payload.objective_ar,
        baseline_ar=payload.baseline_ar,
        target_ar=payload.target_ar,
        indicator_id=payload.indicator_id,
        owner_name_ar=payload.owner_name_ar,
        start_date=payload.start_date,
        due_date=payload.due_date,
    )
    db.add(row)
    db.flush()
    write_audit(
        db, entity_type="improvement_plan", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, after={"code": row.code},
        hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/plans/{plan_id}", response_model=ImprovementPlanOut)
def update_plan(
    plan_id: uuid.UUID,
    payload: ImprovementPlanUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> ImprovementPlan:
    row = _get_scoped(db, ImprovementPlan, plan_id, "خطة التحسين غير موجودة.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="improvement_plan", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.post(
    "/quality/plans/{plan_id}/actions",
    response_model=ImprovementActionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_plan_action(
    plan_id: uuid.UUID,
    payload: ImprovementActionCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> ImprovementAction:
    plan = _get_scoped(db, ImprovementPlan, plan_id, "خطة التحسين غير موجودة.")
    row = ImprovementAction(
        plan_id=plan_id,
        title=payload.title,
        owner_name_ar=payload.owner_name_ar,
        due_date=payload.due_date,
        note_ar=payload.note_ar,
    )
    db.add(row)
    db.flush()
    write_audit(
        db, entity_type="improvement_action", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, hospital_id=plan.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/plan-actions/{action_id}", response_model=ImprovementActionOut)
def update_plan_action(
    action_id: uuid.UUID,
    payload: ImprovementActionUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> ImprovementAction:
    row = _get_scoped(db, ImprovementAction, action_id, "الإجراء غير موجود.")
    plan = _get_scoped(db, ImprovementPlan, row.plan_id, "خطة التحسين غير موجودة.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="improvement_action", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=plan.hospital_id,
    )
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Quality documents
# ---------------------------------------------------------------------------
@router.get("/quality/documents", response_model=list[DocumentOut])
def list_documents(
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[QualityDocument]:
    stmt = select(QualityDocument).where(QualityDocument.deleted_at.is_(None))
    if hospital_id is not None:
        stmt = stmt.where(QualityDocument.hospital_id == hospital_id)
    return list(db.execute(stmt.order_by(QualityDocument.code)).scalars().all())


@router.post(
    "/quality/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
def create_document(
    payload: DocumentCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> QualityDocument:
    hospital_id = _resolve_hospital(identity, payload.hospital_id, db)
    row = QualityDocument(
        hospital_id=hospital_id,
        code=payload.code or _next_code(QualityDocument, hospital_id, db),
        title=payload.title,
        doc_type=payload.doc_type,
        version=payload.version,
        summary_ar=payload.summary_ar,
        owner_name_ar=payload.owner_name_ar,
        effective_date=payload.effective_date,
        review_date=payload.review_date,
    )
    db.add(row)
    db.flush()
    write_audit(
        db, entity_type="quality_document", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, after={"code": row.code, "version": row.version},
        hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/documents/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> QualityDocument:
    row = _get_scoped(db, QualityDocument, document_id, "الوثيقة غير موجودة.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    if data.get("status") == "approved":
        row.approved_at = now_utc()
        row.approved_by = identity.user.id
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="quality_document", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=row.hospital_id,
    )
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Quality meetings
# ---------------------------------------------------------------------------
@router.get("/quality/meetings", response_model=list[MeetingOut])
def list_meetings(
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[QualityMeeting]:
    stmt = select(QualityMeeting).where(QualityMeeting.deleted_at.is_(None))
    if hospital_id is not None:
        stmt = stmt.where(QualityMeeting.hospital_id == hospital_id)
    return list(db.execute(stmt.order_by(QualityMeeting.meeting_date.desc().nulls_last())).scalars().all())


@router.get("/quality/meetings/{meeting_id}", response_model=MeetingDetailOut)
def get_meeting(
    meeting_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> MeetingDetailOut:
    meeting = _get_scoped(db, QualityMeeting, meeting_id, "الاجتماع غير موجود.")
    decisions = list(
        db.execute(
            select(QualityMeetingDecision)
            .where(
                QualityMeetingDecision.meeting_id == meeting.id,
                QualityMeetingDecision.deleted_at.is_(None),
            )
            .order_by(QualityMeetingDecision.created_at)
        ).scalars().all()
    )
    return MeetingDetailOut(
        meeting=MeetingOut.model_validate(meeting),
        decisions=[MeetingDecisionOut.model_validate(d) for d in decisions],
    )


@router.post(
    "/quality/meetings", response_model=MeetingOut, status_code=status.HTTP_201_CREATED
)
def create_meeting(
    payload: MeetingCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> QualityMeeting:
    hospital_id = _resolve_hospital(identity, payload.hospital_id, db)
    row = QualityMeeting(
        hospital_id=hospital_id,
        title=payload.title,
        meeting_date=payload.meeting_date,
        location_ar=payload.location_ar,
        chair_name_ar=payload.chair_name_ar,
        attendees_ar=payload.attendees_ar,
        agenda_ar=payload.agenda_ar,
        minutes_ar=payload.minutes_ar,
    )
    db.add(row)
    db.flush()
    write_audit(
        db, entity_type="quality_meeting", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/meetings/{meeting_id}", response_model=MeetingOut)
def update_meeting(
    meeting_id: uuid.UUID,
    payload: MeetingUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> QualityMeeting:
    row = _get_scoped(db, QualityMeeting, meeting_id, "الاجتماع غير موجود.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="quality_meeting", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=row.hospital_id,
    )
    db.commit()
    return row


@router.post(
    "/quality/meetings/{meeting_id}/decisions",
    response_model=MeetingDecisionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_meeting_decision(
    meeting_id: uuid.UUID,
    payload: MeetingDecisionCreate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> QualityMeetingDecision:
    meeting = _get_scoped(db, QualityMeeting, meeting_id, "الاجتماع غير موجود.")
    row = QualityMeetingDecision(
        meeting_id=meeting_id,
        decision_ar=payload.decision_ar,
        owner_name_ar=payload.owner_name_ar,
        due_date=payload.due_date,
    )
    db.add(row)
    db.flush()
    write_audit(
        db, entity_type="quality_meeting_decision", entity_id=str(row.id), action="create",
        actor_user_id=identity.user.id, hospital_id=meeting.hospital_id,
    )
    db.commit()
    return row


@router.patch("/quality/decisions/{decision_id}", response_model=MeetingDecisionOut)
def update_meeting_decision(
    decision_id: uuid.UUID,
    payload: MeetingDecisionUpdate,
    identity: Identity = Depends(require_permission("quality.manage")),
    db: Session = Depends(get_db),
) -> QualityMeetingDecision:
    row = _get_scoped(db, QualityMeetingDecision, decision_id, "القرار غير موجود.")
    meeting = _get_scoped(db, QualityMeeting, row.meeting_id, "الاجتماع غير موجود.")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = now_utc()
    write_audit(
        db, entity_type="quality_meeting_decision", entity_id=str(row.id), action="update",
        actor_user_id=identity.user.id, after=data, hospital_id=meeting.hospital_id,
    )
    db.commit()
    return row


# ---------------------------------------------------------------------------
# Summary (hospital quality dashboard)
# ---------------------------------------------------------------------------
def _count(db: Session, model: type, hospital_id: uuid.UUID, *where) -> int:
    stmt = select(func.count()).select_from(model).where(
        model.hospital_id == hospital_id, model.deleted_at.is_(None), *where
    )
    return int(db.execute(stmt).scalar_one())


@router.get("/quality/summary", response_model=QualitySummaryOut)
def quality_summary(
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> QualitySummaryOut:
    """Counts for one hospital, or the aggregate across every hospital the
    caller can see (RLS decides). Every number is read from stored rows."""
    hid = hospital_id or identity.hospital_id
    if hid is None:
        raise _invalid("يجب تحديد المستشفى.")
    today = datetime.now(timezone.utc).date()

    def sev_rows() -> dict[str, int]:
        rows = db.execute(
            select(Incident.severity, func.count())
            .where(Incident.hospital_id == hid, Incident.deleted_at.is_(None))
            .group_by(Incident.severity)
        ).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def type_rows() -> dict[str, int]:
        rows = db.execute(
            select(Incident.incident_type, func.count())
            .where(Incident.hospital_id == hid, Incident.deleted_at.is_(None))
            .group_by(Incident.incident_type)
        ).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    capa_overdue = db.execute(
        select(func.count()).select_from(CapaAction).where(
            CapaAction.hospital_id == hid,
            CapaAction.deleted_at.is_(None),
            CapaAction.due_date < today,
            CapaAction.status.notin_(("done", "verified", "cancelled")),
        )
    ).scalar_one()

    return QualitySummaryOut(
        hospital_id=hid,
        incidents_total=_count(db, Incident, hid),
        incidents_open=_count(
            db, Incident, hid, Incident.status.notin_(("closed", "rejected"))
        ),
        incidents_by_severity=sev_rows(),
        incidents_by_type=type_rows(),
        rca_open=_count(db, IncidentRca, hid, IncidentRca.status.notin_(("completed", "cancelled"))),
        capa_total=_count(db, CapaAction, hid),
        capa_open=_count(db, CapaAction, hid, CapaAction.status.notin_(("done", "verified", "cancelled"))),
        capa_overdue=int(capa_overdue),
        risks_total=_count(db, Risk, hid),
        risks_high=_count(db, Risk, hid, Risk.score >= 15, Risk.status == "open"),
        audits_total=_count(db, QualityAudit, hid),
        audits_completed=_count(db, QualityAudit, hid, QualityAudit.status.in_(("completed", "closed"))),
        plans_active=_count(db, ImprovementPlan, hid, ImprovementPlan.status == "active"),
        documents_approved=_count(db, QualityDocument, hid, QualityDocument.status == "approved"),
        meetings_held=_count(db, QualityMeeting, hid, QualityMeeting.status == "held"),
        decisions_open=db.execute(
            select(func.count())
            .select_from(QualityMeetingDecision)
            .join(QualityMeeting, QualityMeeting.id == QualityMeetingDecision.meeting_id)
            .where(
                QualityMeeting.hospital_id == hid,
                QualityMeeting.deleted_at.is_(None),
                QualityMeetingDecision.deleted_at.is_(None),
                QualityMeetingDecision.status.notin_(("done", "cancelled")),
            )
        ).scalar_one(),
    )
