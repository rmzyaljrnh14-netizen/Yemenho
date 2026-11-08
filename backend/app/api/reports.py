"""Reports, dashboards and exports (v0.5).

Everything here is read-only and runs inside the caller's RLS scope: a hospital
user only ever sees their own hospital, a governorate office sees its hospitals,
and the central administration sees all of them. Guarded by ``report.view``.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.base import get_db
from app.models.core import Hospital
from app.services import analytics, export
from app.services.identity import Identity

router = APIRouter(tags=["reports"])

DEMO_NOTE = "بيانات تجريبية — لا تمثّل أرقاماً حقيقية."


def _resolve_hospital_id(identity: Identity, requested: uuid.UUID | None) -> uuid.UUID | None:
    """Clamp a requested hospital to what the caller's scope allows."""
    if identity.is_central:
        return requested
    if identity.hospital_id is not None:
        if requested is not None and requested != identity.hospital_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message_ar": "لا تملك صلاحية على هذا المستشفى."},
            )
        return identity.hospital_id
    # governorate scope (or other) without a single hospital: keep requested,
    # RLS already limits the rows.
    return requested


@router.get("/reports/overview")
def reports_overview(
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    identity: Identity = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
) -> dict:
    return analytics.national_overview(db, year, month)


@router.get("/reports/hospital/{hospital_id}")
def reports_hospital(
    hospital_id: uuid.UUID,
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    identity: Identity = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
) -> dict:
    scope_id = _resolve_hospital_id(identity, hospital_id)
    if scope_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "validation_failed", "message_ar": "معرّف المستشفى مطلوب."},
        )
    hospital = db.get(Hospital, scope_id)
    if hospital is None or hospital.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المستشفى غير موجود."},
        )
    summary = analytics.hospital_summary(db, scope_id, year, month)
    return {
        "hospital_id": summary.hospital_id,
        "hospital_name_ar": summary.hospital_name_ar,
        "period_id": summary.period_id,
        "period_status": summary.period_status,
        "indicators_total": summary.indicators_total,
        "indicators_with_value": summary.indicators_with_value,
        "indicators_met": summary.indicators_met,
        "indicators_at_risk": summary.indicators_at_risk,
        "indicators_unknown": summary.indicators_unknown,
        "compliance_percent": summary.compliance_percent,
        "points": [p.__dict__ for p in summary.points],
    }


@router.get("/reports/trend")
def reports_trend(
    indicator_id: uuid.UUID,
    hospital_id: uuid.UUID | None = Query(default=None),
    months: int = Query(default=12, ge=1, le=36),
    identity: Identity = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
) -> dict:
    scope_id = _resolve_hospital_id(identity, hospital_id)
    if scope_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "validation_failed", "message_ar": "معرّف المستشفى مطلوب."},
        )
    series = analytics.indicator_trend(db, indicator_id, scope_id, months)
    return {
        "indicator_id": indicator_id,
        "hospital_id": scope_id,
        "points": [{"period_label": p.period_label, "year": p.year, "month": p.month, "value": p.value} for p in series],
    }


@router.get("/reports/compare")
def reports_compare(
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    identity: Identity = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
) -> dict:
    rows = analytics.hospital_comparison(db, year, month)
    return {
        "year": year,
        "month": month,
        "hospitals": [
            {
                "hospital_id": r.hospital_id,
                "hospital_name_ar": r.hospital_name_ar,
                "governorate_name_ar": r.governorate_name_ar,
                "reported": r.reported,
                "period_status": r.period_status,
                "compliance_percent": r.compliance_percent,
                "indicators_met": r.indicators_met,
                "indicators_with_value": r.indicators_with_value,
            }
            for r in rows
        ],
    }


@router.get("/reports/late")
def reports_late(
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    identity: Identity = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
) -> dict:
    return {"year": year, "month": month, "hospitals": analytics.late_hospitals(db, year, month)}


def _report_dataset(
    db: Session, year: int, month: int | None, hospital_id: uuid.UUID | None
) -> tuple[str, str, list[str], list[list[object]]]:
    rows = analytics.report_rows(db, year, month, hospital_id)
    period = f"{year}-{month:02d}" if month else str(year)
    title = "تقرير مؤشرات الجودة وسلامة المرضى"
    subtitle = f"الفترة: {period} · تاريخ الإنشاء: {analytics.generated_at_label()}"
    columns = [
        "المستشفى",
        "المحافظة",
        "رمز المؤشر",
        "المؤشر",
        "القسم",
        "القيمة",
        "الوحدة",
        "الهدف",
        "التقييم",
        "الاتجاه",
    ]
    data = [
        [
            r["hospital_name_ar"],
            r["governorate_name_ar"],
            r["indicator_code"],
            r["indicator_name_ar"],
            r["department_name_ar"],
            analytics.fmt_value(r["value"]),
            r["unit_ar"],
            analytics.fmt_value(r["target_value"]),
            r["assessment_label_ar"],
            r["movement_label_ar"],
        ]
        for r in rows
    ]
    return title, subtitle, columns, data


@router.get("/reports/export.xlsx")
def export_xlsx(
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
) -> Response:
    scope_id = _resolve_hospital_id(identity, hospital_id)
    title, subtitle, columns, data = _report_dataset(db, year, month, scope_id)
    content = export.build_excel(
        title=title, subtitle=subtitle, columns=columns, rows=data, sheet_name="المؤشرات"
    )
    filename = f"report-{year}-{month or 'all'}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/export.pdf")
def export_pdf(
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
) -> Response:
    scope_id = _resolve_hospital_id(identity, hospital_id)
    title, subtitle, columns, data = _report_dataset(db, year, month, scope_id)
    content = export.build_pdf(
        title=title,
        subtitle=subtitle,
        columns=columns,
        rows=data,
        note=DEMO_NOTE,
        footer=f"أُنشئ آلياً بواسطة النظام الوطني لإدارة مؤشرات الأداء الصحي · {analytics.generated_at_label()}",
    )
    filename = f"report-{year}-{month or 'all'}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
