"""Reporting periods, indicator values and the review workflow (v0.4).

Workflow: draft -> submitted -> reviewed -> approved, or returned back to draft.
Only a draft (or a returned period) can have its values changed; approved data
is frozen so it cannot be silently overwritten.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_identity, require_permission
from app.db.base import get_db
from app.models.core import (
    Hospital,
    Indicator,
    IndicatorAssignment,
    IndicatorValue,
    IndicatorValueRevision,
    ReportingPeriod,
)
from app.schemas import (
    PeriodCreate,
    PeriodDetailOut,
    PeriodOut,
    RevisionOut,
    StatusChangeRequest,
    ValueAssessmentOut,
    ValueOut,
    ValueUpsert,
    ValueWithMetaOut,
)
from app.services.identity import Identity, now_utc, write_audit
from app.services.indicators import CalculationError, assess, compute_value
from app.services.sync import period_payload, record_change, value_payload

router = APIRouter(tags=["reporting"])

EDITABLE_STATUSES = {"draft", "returned"}


def _effective_target(indicator: Indicator, assignment: IndicatorAssignment | None) -> float | None:
    if assignment is not None and assignment.target_override is not None:
        return float(assignment.target_override)
    return float(indicator.target_value) if indicator.target_value is not None else None


def _get_period(db: Session, period_id: uuid.UUID) -> ReportingPeriod:
    period = db.get(ReportingPeriod, period_id)
    if period is None or period.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "فترة التقرير غير موجودة."},
        )
    return period


def _require_editable(period: ReportingPeriod) -> None:
    if period.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "period_locked",
                "message_ar": "لا يمكن تعديل بيانات فترة مُرسلة أو معتمدة. أعدها إلى مسودة أولاً.",
            },
        )


# ---- Periods ----
@router.get("/periods", response_model=list[PeriodOut])
def list_periods(
    hospital_id: uuid.UUID | None = Query(default=None),
    year: int | None = Query(default=None),
    period_status: str | None = Query(default=None, alias="status"),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[ReportingPeriod]:
    stmt = select(ReportingPeriod).where(ReportingPeriod.deleted_at.is_(None))
    if hospital_id:
        stmt = stmt.where(ReportingPeriod.hospital_id == hospital_id)
    if year:
        stmt = stmt.where(ReportingPeriod.year == year)
    if period_status:
        stmt = stmt.where(ReportingPeriod.status == period_status)
    stmt = stmt.order_by(
        ReportingPeriod.year.desc(),
        ReportingPeriod.month.desc().nullslast(),
        ReportingPeriod.quarter.desc().nullslast(),
    )
    return list(db.execute(stmt).scalars().all())


@router.post("/periods", response_model=PeriodOut, status_code=status.HTTP_201_CREATED)
def create_period(
    payload: PeriodCreate,
    identity: Identity = Depends(require_permission("indicator.enter")),
    db: Session = Depends(get_db),
) -> ReportingPeriod:
    hosp = db.get(Hospital, payload.hospital_id)
    if hosp is None or hosp.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المستشفى غير موجود."},
        )
    if payload.period_type == "monthly" and payload.month is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "validation_failed", "message_ar": "الشهر مطلوب للفترة الشهرية."},
        )
    if payload.period_type == "quarterly" and payload.quarter is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "validation_failed", "message_ar": "الربع مطلوب للفترة الربعية."},
        )
    existing = db.execute(
        select(ReportingPeriod).where(
            ReportingPeriod.hospital_id == payload.hospital_id,
            ReportingPeriod.period_type == payload.period_type,
            ReportingPeriod.year == payload.year,
            ReportingPeriod.month.is_(None) if payload.month is None else ReportingPeriod.month == payload.month,
            ReportingPeriod.quarter.is_(None)
            if payload.quarter is None
            else ReportingPeriod.quarter == payload.quarter,
            ReportingPeriod.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    period = ReportingPeriod(
        hospital_id=payload.hospital_id,
        period_type=payload.period_type,
        year=payload.year,
        month=payload.month,
        quarter=payload.quarter,
    )
    db.add(period)
    db.flush()
    write_audit(
        db, entity_type="reporting_period", entity_id=str(period.id), action="create",
        actor_user_id=identity.user.id,
        after={"hospital_id": str(period.hospital_id), "year": period.year, "month": period.month},
        hospital_id=period.hospital_id,
    )
    record_change(
        db, entity_type="reporting_period", entity_id=str(period.id), op="upsert",
        rev=period.rev, hospital_id=period.hospital_id, payload=period_payload(period),
    )
    db.commit()
    return period


@router.get("/periods/{period_id}", response_model=PeriodDetailOut)
def get_period(
    period_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> PeriodDetailOut:
    period = _get_period(db, period_id)
    rows = db.execute(
        select(IndicatorValue, Indicator)
        .join(Indicator, Indicator.id == IndicatorValue.indicator_id)
        .where(IndicatorValue.period_id == period_id, IndicatorValue.deleted_at.is_(None))
        .order_by(Indicator.code)
    ).all()
    values: list[ValueWithMetaOut] = []
    for value, indicator in rows:
        a = assess(
            direction=indicator.direction,
            value=float(value.value) if value.value is not None else None,
            target_value=float(indicator.target_value) if indicator.target_value is not None else None,
            acceptable_min=float(indicator.acceptable_min) if indicator.acceptable_min is not None else None,
            acceptable_max=float(indicator.acceptable_max) if indicator.acceptable_max is not None else None,
        )
        values.append(
            ValueWithMetaOut(
                **ValueOut.model_validate(value).model_dump(),
                assessment=ValueAssessmentOut(status=a.status, label_ar=a.label_ar, message_ar=a.message_ar),
            )
        )
    return PeriodDetailOut(period=PeriodOut.model_validate(period), values=values)


# ---- Values ----
@router.put("/periods/{period_id}/values", response_model=ValueOut)
def upsert_value(
    period_id: uuid.UUID,
    payload: ValueUpsert,
    identity: Identity = Depends(require_permission("indicator.enter")),
    db: Session = Depends(get_db),
) -> IndicatorValue:
    period = _get_period(db, period_id)
    _require_editable(period)

    indicator = db.get(Indicator, payload.indicator_id)
    if indicator is None or indicator.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المؤشر غير موجود."},
        )
    if payload.department_id is not None:
        assignment = db.execute(
            select(IndicatorAssignment).where(
                IndicatorAssignment.indicator_id == payload.indicator_id,
                IndicatorAssignment.hospital_id == period.hospital_id,
                IndicatorAssignment.department_id == payload.department_id,
                IndicatorAssignment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if assignment is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "not_assigned", "message_ar": "المؤشر غير مُسند لهذا القسم."},
            )

    try:
        computed, value_type = compute_value(
            computation=indicator.computation,
            numerator=payload.numerator,
            denominator=payload.denominator,
            multiplier=float(indicator.multiplier) if indicator.multiplier is not None else 1,
            entered_value=payload.entered_value,
        )
    except CalculationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "validation_failed", "message_ar": "طريقة حساب المؤشر غير مدعومة."},
        )

    existing = db.execute(
        select(IndicatorValue).where(
            IndicatorValue.period_id == period_id,
            IndicatorValue.indicator_id == payload.indicator_id,
            IndicatorValue.department_id.is_(None)
            if payload.department_id is None
            else IndicatorValue.department_id == payload.department_id,
            IndicatorValue.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if existing is None:
        value = IndicatorValue(
            period_id=period_id,
            indicator_id=payload.indicator_id,
            department_id=payload.department_id,
            numerator=payload.numerator,
            denominator=payload.denominator,
            value=computed,
            value_type=value_type,
            note=payload.note,
            created_by=identity.user.id,
        )
        db.add(value)
        db.flush()
        db.add(
            IndicatorValueRevision(
                value_id=value.id, action="create", new_value=computed,
                new_numerator=payload.numerator, new_denominator=payload.denominator,
                note=payload.note, actor_user_id=identity.user.id,
            )
        )
        record_change(
            db, entity_type="indicator_value", entity_id=str(value.id), op="upsert",
            rev=value.rev, hospital_id=period.hospital_id, payload=value_payload(value),
        )
        db.commit()
        return value

    db.add(
        IndicatorValueRevision(
            value_id=existing.id, action="update",
            old_value=existing.value, new_value=computed,
            old_numerator=existing.numerator, new_numerator=payload.numerator,
            old_denominator=existing.denominator, new_denominator=payload.denominator,
            note=payload.note, actor_user_id=identity.user.id,
        )
    )
    existing.numerator = payload.numerator
    existing.denominator = payload.denominator
    existing.value = computed
    existing.value_type = value_type
    existing.note = payload.note
    existing.rev += 1
    record_change(
        db, entity_type="indicator_value", entity_id=str(existing.id), op="upsert",
        rev=existing.rev, hospital_id=period.hospital_id, payload=value_payload(existing),
    )
    db.commit()
    return existing


@router.delete("/periods/{period_id}/values/{value_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_value(
    period_id: uuid.UUID,
    value_id: uuid.UUID,
    identity: Identity = Depends(require_permission("indicator.enter")),
    db: Session = Depends(get_db),
) -> None:
    period = _get_period(db, period_id)
    _require_editable(period)
    value = db.get(IndicatorValue, value_id)
    if value is None or value.period_id != period_id or value.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "القيمة غير موجودة."},
        )
    value.deleted_at = now_utc()
    value.rev += 1
    db.add(
        IndicatorValueRevision(
            value_id=value.id, action="delete", old_value=value.value, actor_user_id=identity.user.id
        )
    )
    record_change(
        db, entity_type="indicator_value", entity_id=str(value.id), op="delete",
        rev=value.rev, hospital_id=period.hospital_id, payload=value_payload(value),
    )
    db.commit()


@router.get("/values/{value_id}/revisions", response_model=list[RevisionOut])
def list_revisions(
    value_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[IndicatorValueRevision]:
    value = db.get(IndicatorValue, value_id)
    if value is None or value.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "القيمة غير موجودة."},
        )
    return list(
        db.execute(
            select(IndicatorValueRevision)
            .where(IndicatorValueRevision.value_id == value_id)
            .order_by(IndicatorValueRevision.at.desc())
        ).scalars().all()
    )


# ---- Workflow ----
def _transition(
    db: Session,
    period: ReportingPeriod,
    identity: Identity,
    *,
    action: str,
    from_statuses: set[str],
    to_status: str,
    permission: str,
    note: str | None,
) -> ReportingPeriod:
    if not identity.has(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message_ar": "لا تملك صلاحية لهذا الإجراء."},
        )
    if period.status not in from_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_transition",
                "message_ar": f"لا يمكن تنفيذ هذا الإجراء والفترة في حالة «{period.status}».",
            },
        )
    now = now_utc()
    period.status = to_status
    if action == "submit":
        period.submitted_at, period.submitted_by = now, identity.user.id
    elif action == "review":
        period.reviewed_at, period.reviewed_by = now, identity.user.id
    elif action == "approve":
        period.approved_at, period.approved_by = now, identity.user.id
    elif action == "return":
        period.returned_at, period.returned_by = now, identity.user.id
    if note:
        period.note = note
    period.rev += 1
    write_audit(
        db, entity_type="reporting_period", entity_id=str(period.id), action=action,
        actor_user_id=identity.user.id, after={"status": to_status},
        hospital_id=period.hospital_id,
    )
    record_change(
        db, entity_type="reporting_period", entity_id=str(period.id), op="upsert",
        rev=period.rev, hospital_id=period.hospital_id, payload=period_payload(period),
    )
    db.commit()
    return period


@router.post("/periods/{period_id}/submit", response_model=PeriodOut)
def submit_period(
    period_id: uuid.UUID,
    payload: StatusChangeRequest | None = None,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> ReportingPeriod:
    period = _get_period(db, period_id)
    return _transition(
        db, period, identity, action="submit", from_statuses={"draft", "returned"},
        to_status="submitted", permission="period.submit", note=payload.note if payload else None,
    )


@router.post("/periods/{period_id}/review", response_model=PeriodOut)
def review_period(
    period_id: uuid.UUID,
    payload: StatusChangeRequest | None = None,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> ReportingPeriod:
    period = _get_period(db, period_id)
    return _transition(
        db, period, identity, action="review", from_statuses={"submitted"},
        to_status="reviewed", permission="period.review", note=payload.note if payload else None,
    )


@router.post("/periods/{period_id}/approve", response_model=PeriodOut)
def approve_period(
    period_id: uuid.UUID,
    payload: StatusChangeRequest | None = None,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> ReportingPeriod:
    period = _get_period(db, period_id)
    return _transition(
        db, period, identity, action="approve", from_statuses={"submitted", "reviewed"},
        to_status="approved", permission="period.approve", note=payload.note if payload else None,
    )


@router.post("/periods/{period_id}/return", response_model=PeriodOut)
def return_period(
    period_id: uuid.UUID,
    payload: StatusChangeRequest | None = None,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> ReportingPeriod:
    period = _get_period(db, period_id)
    return _transition(
        db, period, identity, action="return", from_statuses={"submitted", "reviewed", "approved"},
        to_status="returned", permission="period.review", note=payload.note if payload else None,
    )
