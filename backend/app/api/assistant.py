"""Assistant endpoints (v0.8).

A read-only aid that analyses the data the caller can already see: trends,
statistical anomalies, late submissions, quality pressure and improvement areas,
plus a plain-text draft report. Every finding carries the numbers it came from.

Nothing here invents data. The optional language model (``ai_narrator``) only
rewrites the finished findings into smoother Arabic; when it is off, the computed
findings are returned as they are. Guarded by ``assistant.use`` and scoped by RLS
exactly like the rest of the API.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.base import get_db
from app.models.core import Hospital
from app.services import ai_narrator, insights
from app.services.identity import Identity

router = APIRouter(tags=["assistant"])

NOT_CONFIGURED_NOTE_AR = (
    "المساعد يعمل بالتحليل الآلي المدمج. لم يُفعَّل نموذج لغوي، لذا تُعرض النتائج "
    "المحسوبة كما هي دون صياغة إضافية. كل الأرقام مشتقة من البيانات المسجّلة."
)
ENABLED_NOTE_AR = (
    "المساعد يعمل بالتحليل الآلي المدمج، مع صياغة لغوية اختيارية للنتائج المحسوبة فقط. "
    "لا يضيف النموذج أي رقم أو سبب غير موجود في البيانات."
)


def _resolve_hospital(identity: Identity, requested: uuid.UUID, db: Session) -> uuid.UUID:
    if identity.is_central:
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
    if requested != identity.hospital_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message_ar": "لا تملك صلاحية على هذا المستشفى."},
        )
    return identity.hospital_id


def _narrative_payload(bundle: dict) -> dict:
    """A small, bounded view of the findings for the narrator. No raw rows."""
    return {
        "scope": "hospital" if "hospital_name_ar" in bundle else "national",
        "period": {"year": bundle.get("year"), "month": bundle.get("month")},
        "numbers": {
            k: bundle.get(k)
            for k in (
                "hospital_name_ar",
                "compliance_percent",
                "indicators_with_value",
                "indicators_met",
                "indicators_at_risk",
                "hospitals_total",
                "hospitals_reported",
            )
            if k in bundle
        },
        "findings": [
            {"severity": i["severity"], "title": i["title_ar"], "detail": i["detail_ar"]}
            for i in bundle.get("insights", [])
        ],
        "improvement_areas": bundle.get("improvement_areas", []),
        "disclaimer_ar": bundle["disclaimer_ar"],
    }


@router.get("/assistant/status")
def assistant_status(
    identity: Identity = Depends(require_permission("assistant.use")),
) -> dict:
    configured = ai_narrator.is_configured()
    return {
        "enabled": True,
        "model_configured": configured,
        "narrative_available": configured,
        "note_ar": ENABLED_NOTE_AR if configured else NOT_CONFIGURED_NOTE_AR,
    }


@router.get("/assistant/national")
def assistant_national(
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    identity: Identity = Depends(require_permission("assistant.use")),
    db: Session = Depends(get_db),
) -> dict:
    bundle = insights.national_insight_bundle(db, year, month)
    bundle["narrative_ar"] = ai_narrator.narrate(_narrative_payload(bundle))
    return bundle


@router.get("/assistant/hospital/{hospital_id}")
def assistant_hospital(
    hospital_id: uuid.UUID,
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    identity: Identity = Depends(require_permission("assistant.use")),
    db: Session = Depends(get_db),
) -> dict:
    scope_id = _resolve_hospital(identity, hospital_id, db)
    bundle = insights.hospital_insight_bundle(db, scope_id, year, month)
    bundle["narrative_ar"] = ai_narrator.narrate(_narrative_payload(bundle))
    return bundle


@router.get("/assistant/hospital/{hospital_id}/draft-report")
def assistant_draft_report(
    hospital_id: uuid.UUID,
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    identity: Identity = Depends(require_permission("assistant.use")),
    db: Session = Depends(get_db),
) -> dict:
    scope_id = _resolve_hospital(identity, hospital_id, db)
    hospital = db.get(Hospital, scope_id)
    name = hospital.name_ar if hospital else "—"
    text = insights.build_hospital_report_text(db, scope_id, year, month)
    return {
        "hospital_id": scope_id,
        "hospital_name_ar": name,
        "year": year,
        "month": month,
        "report_text_ar": text,
        "disclaimer_ar": insights.DISCLAIMER_AR,
        "generated_at": insights._now(),
    }
