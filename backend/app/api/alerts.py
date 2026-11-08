"""Alert-centre endpoints (v0.9).

Read the unified alert list (computed from stored rows) and acknowledge or
reopen a single alert. Viewing reuses ``report.view``; acknowledging requires
``alert.manage``, so a read-only user sees the list but cannot change it.

Every row is scoped by RLS and by the caller's hospital exactly like the rest of
the API, and the alert list is never stored — only the acknowledgement is.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_identity, require_permission
from app.db.base import get_db
from app.db.context import apply_rls_context
from app.models.core import AlertAcknowledgement, Hospital
from app.schemas import (
    AlertAckRequest,
    AlertListOut,
    AlertOut,
    AlertRuleCatalogueOut,
    AlertRuleOut,
    AlertRuleUpdate,
)
from app.services import alerts as alerts_service
from app.services import alert_rules as alert_rules_service
from app.services.identity import Identity

router = APIRouter(tags=["alerts"])

NOTES_MAX = 500


def _resolve_scope_hospital(identity: Identity, requested: uuid.UUID | None, db: Session) -> uuid.UUID | None:
    """Decide which hospital the caller is asking about (None = national)."""
    if identity.is_central:
        if requested is None:
            return None
        hosp = db.get(Hospital, requested)
        if hosp is None or hosp.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "not_found", "message_ar": "المستشفى غير موجود."},
            )
        return requested
    if identity.hospital_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message_ar": "لا يرتبط حسابك بمستشفى."},
        )
    if requested is not None and requested != identity.hospital_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message_ar": "لا تملك صلاحية على هذا المستشفى."},
        )
    return identity.hospital_id


def _to_out(a: alerts_service.Alert) -> AlertOut:
    return AlertOut(
        key=a.key,
        kind=a.kind,
        source=a.source,
        source_label_ar=alerts_service.SOURCE_LABEL_AR.get(a.source, a.source),
        severity=a.severity,
        title_ar=a.title_ar,
        detail_ar=a.detail_ar,
        hospital_id=a.hospital_id,
        hospital_name_ar=a.hospital_name_ar,
        period_year=a.period_year,
        period_month=a.period_month,
        basis=a.basis,
        acked=a.acked,
        acked_by_name=a.acked_by_name,
        acked_at=a.acked_at,
        note_ar=a.note_ar,
    )


@router.get("/alerts", response_model=AlertListOut)
def list_alerts(
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    hospital_id: uuid.UUID | None = Query(default=None),
    include_acked: bool = Query(default=True),
    identity: Identity = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
) -> AlertListOut:
    scope_id = _resolve_scope_hospital(identity, hospital_id, db)
    items = alerts_service.build_alerts(db, identity, year, month, scope_id)
    if not include_acked:
        items = [a for a in items if not a.acked]
    return AlertListOut(
        year=year,
        month=month,
        scope="hospital" if scope_id else "national",
        summary=alerts_service.summarise(items),
        alerts=[_to_out(a) for a in items],
    )


def _find_ack(db: Session, key: str) -> AlertAcknowledgement | None:
    return db.execute(
        select(AlertAcknowledgement).where(
            AlertAcknowledgement.alert_key == key,
            AlertAcknowledgement.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


@router.post("/alerts/{key}/ack", response_model=AlertOut)
def acknowledge_alert(
    key: str,
    payload: AlertAckRequest,
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(require_permission("alert.manage")),
    db: Session = Depends(get_db),
) -> AlertOut:
    """Acknowledge one computed alert. The alert must exist in the current list."""
    scope_id = _resolve_scope_hospital(identity, hospital_id, db)
    items = alerts_service.build_alerts(db, identity, year, month, scope_id)
    target = next((a for a in items if a.key == key), None)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "التنبيه غير موجود في هذه الفترة."},
        )
    if target.hospital_id is None:
        # National alerts carry no single hospital; they cannot be acknowledged
        # here because the acknowledgement table is hospital-scoped.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "not_hospital_scoped",
                "message_ar": "هذا تنبيه وطني بلا مستشفى محدد ولا يمكن إقراره.",
            },
        )

    now = datetime.now(timezone.utc)
    note = (payload.note_ar or "").strip() or None
    if note is not None and len(note) > NOTES_MAX:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "note_too_long", "message_ar": f"الملاحظة أطول من {NOTES_MAX} حرفاً."},
        )

    ack = _find_ack(db, key)
    if ack is None:
        ack = AlertAcknowledgement(
            alert_key=key,
            hospital_id=target.hospital_id,
            period_year=year,
            period_month=month,
            kind=target.kind,
            severity=target.severity,
            note_ar=note,
            acknowledged_by=identity.user.id,
            acknowledged_at=now,
        )
        db.add(ack)
    else:
        ack.note_ar = note
        ack.acknowledged_by = identity.user.id
        ack.acknowledged_at = now
        ack.updated_at = now
    db.commit()

    target.acked = True
    target.acked_at = now.isoformat()
    target.note_ar = note
    target.acked_by_name = identity.user.display_name
    return _to_out(target)


@router.post("/alerts/{key}/reopen", response_model=AlertOut)
def reopen_alert(
    key: str,
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(require_permission("alert.manage")),
    db: Session = Depends(get_db),
) -> AlertOut:
    """Reopen an acknowledged alert by soft-deleting its acknowledgement."""
    scope_id = _resolve_scope_hospital(identity, hospital_id, db)
    # Resolve the alert while the RLS context is still set: a commit clears the
    # transaction-local context, so the list must be read before we commit.
    items = alerts_service.build_alerts(db, identity, year, month, scope_id)
    target = next((a for a in items if a.key == key), None)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "التنبيه غير موجود في هذه الفترة."},
        )
    ack = _find_ack(db, key)
    if ack is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "لا يوجد إقرار لهذا التنبيه."},
        )
    ack.deleted_at = datetime.now(timezone.utc)
    db.commit()

    target.acked = False
    target.acked_at = None
    target.acked_by_name = None
    target.note_ar = None
    return _to_out(target)


# ---------------------------------------------------------------------------
# Configurable alert rules (v0.10)
# ---------------------------------------------------------------------------
def _to_rule_out(r: dict) -> AlertRuleOut:
    return AlertRuleOut(**r)


def _reapply_rls(db: Session, identity: Identity) -> None:
    """Restore the transaction-local RLS context after a commit (v0.10).

    The write helpers commit, which drops the ``set_config(..., true)`` context.
    The following read of the catalogue would then see no hospital rows, so the
    context is set again before that read.
    """
    apply_rls_context(
        db,
        is_central=identity.is_central,
        hospital_id=str(identity.hospital_id) if identity.hospital_id else None,
        governorate_id=str(identity.governorate_id) if identity.governorate_id else None,
    )


@router.get("/alert-rules", response_model=AlertRuleCatalogueOut)
def get_alert_rules(
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(require_permission("alert.manage")),
    db: Session = Depends(get_db),
) -> AlertRuleCatalogueOut:
    """The catalogue of tunable alert thresholds with their effective values.

    A central user may pass ``hospital_id`` to see that hospital's overrides;
    without it they see the national defaults. A hospital user always sees their
    own hospital's effective rules.
    """
    scope_id = _resolve_scope_hospital(identity, hospital_id, db)
    rules = alert_rules_service.catalogue(db, scope_id)
    return AlertRuleCatalogueOut(
        hospital_id=scope_id,
        scope="hospital" if scope_id else "national",
        rules=[_to_rule_out(r) for r in rules],
        note_ar=(
            "العتبات القابلة للتهيئة تُغيَّر من هنا. التنبيهات نفسها تبقى محسوبة من البيانات "
            "الفعلية ولا تُختلق؛ وتُطبَّق القيم الأكثر تخصيصاً (المستشفى) على القيمة الوطنية على الافتراضي."
        ),
    )


@router.put("/alert-rules/{kind}", response_model=AlertRuleOut)
def update_alert_rule(
    kind: str,
    payload: AlertRuleUpdate,
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(require_permission("alert.configure")),
    db: Session = Depends(get_db),
) -> AlertRuleOut:
    """Set the thresholds (and on/off) for one alert kind.

    Central users set the national default by omitting ``hospital_id``, or a
    hospital override by passing one. A hospital user always edits their own
    hospital. Values are validated and clamped server-side, so a bad edit cannot
    break the engine.
    """
    scope_id = _resolve_scope_hospital(identity, hospital_id, db)
    try:
        alert_rules_service.upsert_rule(
            db,
            kind=kind,
            hospital_id=scope_id,
            params=payload.params,
            is_enabled=payload.is_enabled,
            note_ar=payload.note_ar,
            user_id=identity.user.id,
        )
    except ValueError as exc:
        reason = str(exc)
        if reason == "unknown_kind":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "unknown_kind", "message_ar": "نوع التنبيه غير معروف."},
            )
        if reason == "not_overridable":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "not_overridable",
                    "message_ar": "هذا النوع لا يقبل تخصيصاً لكل مستشفى (يُضبط وطنياً فقط).",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_rule", "message_ar": "قيم غير صالحة."},
        )

    _reapply_rls(db, identity)
    rows = alert_rules_service.catalogue(db, scope_id)
    for r in rows:
        if r["kind"] == kind:
            return _to_rule_out(r)
    # Defensive: kind validated above, so this cannot normally happen.
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "unknown_kind", "message_ar": "نوع التنبيه غير معروف."},
    )


@router.post("/alert-rules/{kind}/reset", response_model=AlertRuleOut)
def reset_alert_rule(
    kind: str,
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(require_permission("alert.configure")),
    db: Session = Depends(get_db),
) -> AlertRuleOut:
    """Clear an override (or a national default) so the next scope applies again."""
    scope_id = _resolve_scope_hospital(identity, hospital_id, db)
    alert_rules_service.reset_rule(db, kind=kind, hospital_id=scope_id)
    _reapply_rls(db, identity)
    rows = alert_rules_service.catalogue(db, scope_id)
    for r in rows:
        if r["kind"] == kind:
            return _to_rule_out(r)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "unknown_kind", "message_ar": "نوع التنبيه غير معروف."},
    )
