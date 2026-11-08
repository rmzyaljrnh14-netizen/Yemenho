"""Analytics for dashboards and reports (v0.5).

Read-only aggregation over the v0.4 data model. All queries run inside the
caller's RLS scope, so a hospital user only ever aggregates their own data and
the central administration aggregates everything it is allowed to see.

Honesty rules carried over from the calculation engine:
  * a missing value is ``None`` and never counted as zero;
  * a percentage is aggregated from summed numerator / summed denominator, not
    by averaging percentages;
  * nothing is invented: an indicator with no data is reported as "no data".
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    Department,
    Hospital,
    Indicator,
    IndicatorAssignment,
    IndicatorValue,
    ReportingPeriod,
)
from app.services.indicators import assess, trend, trend_is_improving

# Statuses that count as "the hospital has sent its data".
REPORTED_STATUSES = ("submitted", "reviewed", "approved")


@dataclass
class IndicatorPoint:
    indicator_id: uuid.UUID
    code: str
    name_ar: str
    direction: str
    unit_ar: str | None
    target_value: float | None
    value: float | None
    assessment_status: str
    assessment_label_ar: str
    movement: str
    improving: bool | None
    department_id: uuid.UUID | None = None
    department_name_ar: str | None = None


@dataclass
class TrendPoint:
    period_label: str
    year: int
    month: int | None
    value: float | None


@dataclass
class HospitalRow:
    hospital_id: uuid.UUID
    hospital_name_ar: str
    governorate_name_ar: str | None
    reported: bool
    period_status: str | None
    last_sync_label: str
    indicators_with_value: int
    indicators_met: int
    indicators_at_risk: int
    compliance_percent: float | None
    rows: list[IndicatorPoint] = field(default_factory=list)


@dataclass
class HospitalSummary:
    hospital_id: uuid.UUID
    hospital_name_ar: str
    period_id: uuid.UUID | None
    period_status: str | None
    indicators_total: int
    indicators_with_value: int
    indicators_met: int
    indicators_at_risk: int
    indicators_unknown: int
    compliance_percent: float | None
    points: list[IndicatorPoint] = field(default_factory=list)


def _as_float(x: object | None) -> float | None:
    return float(x) if x is not None else None


def _movement_is_improving(movement: str, direction: str) -> bool | None:
    return trend_is_improving(movement, direction)


def _month_label(year: int, month: int | None) -> str:
    if month is None:
        return str(year)
    return f"{year}-{month:02d}"


def _points_for_period(
    db: Session,
    period: ReportingPeriod,
    previous: ReportingPeriod | None,
) -> list[IndicatorPoint]:
    """Build one point per (indicator, department) value in a period."""
    rows = db.execute(
        select(IndicatorValue, Indicator)
        .join(Indicator, Indicator.id == IndicatorValue.indicator_id)
        .where(IndicatorValue.period_id == period.id, IndicatorValue.deleted_at.is_(None))
        .order_by(Indicator.code)
    ).all()

    prev_by_key: dict[str, float] = {}
    if previous is not None:
        for value, indicator in db.execute(
            select(IndicatorValue, Indicator)
            .join(Indicator, Indicator.id == IndicatorValue.indicator_id)
            .where(IndicatorValue.period_id == previous.id, IndicatorValue.deleted_at.is_(None))
        ).all():
            prev_by_key[_key(indicator.id, value.department_id)] = _as_float(value.value)  # type: ignore[assignment]

    dept_names = {
        d.id: d.name_ar
        for d in db.execute(select(Department).where(Department.deleted_at.is_(None))).scalars().all()
    }

    points: list[IndicatorPoint] = []
    for value, indicator in rows:
        v = _as_float(value.value)
        a = assess(
            direction=indicator.direction,
            value=v,
            target_value=_as_float(indicator.target_value),
            acceptable_min=_as_float(indicator.acceptable_min),
            acceptable_max=_as_float(indicator.acceptable_max),
        )
        prev = prev_by_key.get(_key(indicator.id, value.department_id))
        movement = trend(v, prev, indicator.direction)
        points.append(
            IndicatorPoint(
                indicator_id=indicator.id,
                code=indicator.code,
                name_ar=indicator.name_ar,
                direction=indicator.direction,
                unit_ar=indicator.unit_ar,
                target_value=_as_float(indicator.target_value),
                value=v,
                assessment_status=a.status,
                assessment_label_ar=a.label_ar,
                movement=movement,
                improving=_movement_is_improving(movement, indicator.direction),
                department_id=value.department_id,
                department_name_ar=dept_names.get(value.department_id) if value.department_id else None,
            )
        )
    return points


def _key(indicator_id: uuid.UUID, department_id: uuid.UUID | None) -> str:
    return f"{indicator_id}:{department_id or ''}"


def _previous_period(db: Session, period: ReportingPeriod) -> ReportingPeriod | None:
    if period.month is not None:
        year, month = period.year, period.month - 1
        if month == 0:
            year, month = year - 1, 12
        return db.execute(
            select(ReportingPeriod).where(
                ReportingPeriod.hospital_id == period.hospital_id,
                ReportingPeriod.period_type == period.period_type,
                ReportingPeriod.year == year,
                ReportingPeriod.month == month,
                ReportingPeriod.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
    if period.quarter is not None:
        year, quarter = period.year, period.quarter - 1
        if quarter == 0:
            year, quarter = year - 1, 4
        return db.execute(
            select(ReportingPeriod).where(
                ReportingPeriod.hospital_id == period.hospital_id,
                ReportingPeriod.period_type == period.period_type,
                ReportingPeriod.year == year,
                ReportingPeriod.quarter == quarter,
                ReportingPeriod.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
    return None


def _score(points: list[IndicatorPoint]) -> tuple[int, int, int, float | None]:
    """Return (with_value, met, at_risk, compliance_percent)."""
    with_value = [p for p in points if p.value is not None]
    met = [p for p in with_value if p.assessment_status == "good"]
    at_risk = [p for p in with_value if p.assessment_status in {"warning", "poor"}]
    compliance = (len(met) / len(with_value) * 100.0) if with_value else None
    return len(with_value), len(met), len(at_risk), (round(compliance, 1) if compliance is not None else None)


def _latest_period(db: Session, hospital_id: uuid.UUID, year: int, month: int | None) -> ReportingPeriod | None:
    stmt = select(ReportingPeriod).where(
        ReportingPeriod.hospital_id == hospital_id,
        ReportingPeriod.year == year,
        ReportingPeriod.deleted_at.is_(None),
    )
    if month is not None:
        stmt = stmt.where(ReportingPeriod.month == month)
    stmt = stmt.order_by(
        ReportingPeriod.month.desc().nullslast(),
        ReportingPeriod.quarter.desc().nullslast(),
    )
    return db.execute(stmt).scalars().first()


def hospital_summary(
    db: Session,
    hospital_id: uuid.UUID,
    year: int,
    month: int | None,
) -> HospitalSummary:
    hospital = db.get(Hospital, hospital_id)
    period = _latest_period(db, hospital_id, year, month)
    if period is None:
        return HospitalSummary(
            hospital_id=hospital_id,
            hospital_name_ar=hospital.name_ar if hospital else "—",
            period_id=None,
            period_status=None,
            indicators_total=0,
            indicators_with_value=0,
            indicators_met=0,
            indicators_at_risk=0,
            indicators_unknown=0,
            compliance_percent=None,
            points=[],
        )
    points = _points_for_period(db, period, _previous_period(db, period))
    with_value, met, at_risk, compliance = _score(points)
    return HospitalSummary(
        hospital_id=hospital_id,
        hospital_name_ar=hospital.name_ar if hospital else "—",
        period_id=period.id,
        period_status=period.status,
        indicators_total=len(points),
        indicators_with_value=with_value,
        indicators_met=met,
        indicators_at_risk=at_risk,
        indicators_unknown=len(points) - with_value,
        compliance_percent=compliance,
        points=points,
    )


def national_overview(db: Session, year: int, month: int | None) -> dict:
    """Aggregate across every hospital the caller can see."""
    hospitals = list(db.execute(select(Hospital).where(Hospital.deleted_at.is_(None))).scalars().all())
    gov_names = _governorate_names(db)

    rows: list[HospitalRow] = []
    totals = {"with_value": 0, "met": 0, "at_risk": 0, "indicators": 0}
    reported_count = 0
    compliance_values: list[float] = []
    by_governorate: dict[str, dict] = {}

    for h in hospitals:
        summary = hospital_summary(db, h.id, year, month)
        reported = summary.period_status in REPORTED_STATUSES
        if reported:
            reported_count += 1
        if summary.compliance_percent is not None:
            compliance_values.append(summary.compliance_percent)
        totals["with_value"] += summary.indicators_with_value
        totals["met"] += summary.indicators_met
        totals["at_risk"] += summary.indicators_at_risk
        totals["indicators"] += summary.indicators_total

        gov = gov_names.get(h.governorate_id) or "غير محدّد"
        bucket = by_governorate.setdefault(
            gov, {"governorate_name_ar": gov, "hospitals": 0, "reported": 0, "met": 0, "with_value": 0}
        )
        bucket["hospitals"] += 1
        bucket["reported"] += 1 if reported else 0
        bucket["met"] += summary.indicators_met
        bucket["with_value"] += summary.indicators_with_value

        rows.append(
            HospitalRow(
                hospital_id=h.id,
                hospital_name_ar=h.name_ar,
                governorate_name_ar=gov_names.get(h.governorate_id),
                reported=reported,
                period_status=summary.period_status,
                last_sync_label=_period_label(summary.period_id, summary.period_status),
                indicators_with_value=summary.indicators_with_value,
                indicators_met=summary.indicators_met,
                indicators_at_risk=summary.indicators_at_risk,
                compliance_percent=summary.compliance_percent,
            )
        )

    for bucket in by_governorate.values():
        bucket["compliance_percent"] = (
            round(bucket["met"] / bucket["with_value"] * 100.0, 1) if bucket["with_value"] else None
        )

    overall_compliance = (
        round(totals["met"] / totals["with_value"] * 100.0, 1) if totals["with_value"] else None
    )
    return {
        "year": year,
        "month": month,
        "hospitals_total": len(hospitals),
        "hospitals_reported": reported_count,
        "indicators_total": totals["indicators"],
        "indicators_with_value": totals["with_value"],
        "indicators_met": totals["met"],
        "indicators_at_risk": totals["at_risk"],
        "compliance_percent": overall_compliance,
        "average_hospital_compliance": (
            round(sum(compliance_values) / len(compliance_values), 1) if compliance_values else None
        ),
        "hospitals": [
            {
                "hospital_id": r.hospital_id,
                "hospital_name_ar": r.hospital_name_ar,
                "governorate_name_ar": r.governorate_name_ar,
                "reported": r.reported,
                "period_status": r.period_status,
                "last_sync_label": r.last_sync_label,
                "indicators_with_value": r.indicators_with_value,
                "indicators_met": r.indicators_met,
                "indicators_at_risk": r.indicators_at_risk,
                "compliance_percent": r.compliance_percent,
            }
            for r in sorted(rows, key=lambda x: (x.compliance_percent is None, -(x.compliance_percent or 0)))
        ],
        "governorates": sorted(by_governorate.values(), key=lambda x: x["governorate_name_ar"]),
    }


def _governorate_names(db: Session) -> dict[uuid.UUID, str]:
    from app.models.core import Organization

    rows = db.execute(
        select(Organization.id, Organization.name_ar).where(
            Organization.level == "governorate", Organization.deleted_at.is_(None)
        )
    ).all()
    return {r[0]: r[1] for r in rows}


def _period_label(period_id: uuid.UUID | None, status: str | None) -> str:
    if period_id is None:
        return "لا توجد بيانات"
    statuses = {
        "draft": "مسودة",
        "submitted": "مُرسلة",
        "reviewed": "مراجَعة",
        "approved": "معتمدة",
        "returned": "مُعادة",
    }
    return f"آخر فترة: {statuses.get(status or '', '—')}"


def indicator_trend(
    db: Session,
    indicator_id: uuid.UUID,
    hospital_id: uuid.UUID,
    months: int = 12,
) -> list[TrendPoint]:
    """Monthly series for one indicator in one hospital, oldest first."""
    periods = list(
        db.execute(
            select(ReportingPeriod)
            .where(
                ReportingPeriod.hospital_id == hospital_id,
                ReportingPeriod.period_type == "monthly",
                ReportingPeriod.deleted_at.is_(None),
            )
            .order_by(ReportingPeriod.year.desc(), ReportingPeriod.month.desc().nullslast())
            .limit(months)
        ).scalars().all()
    )
    periods.reverse()
    series: list[TrendPoint] = []
    for p in periods:
        value = db.execute(
            select(IndicatorValue.value).where(
                IndicatorValue.period_id == p.id,
                IndicatorValue.indicator_id == indicator_id,
                IndicatorValue.department_id.is_(None),
                IndicatorValue.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        series.append(
            TrendPoint(
                period_label=_month_label(p.year, p.month),
                year=p.year,
                month=p.month,
                value=_as_float(value),
            )
        )
    return series


def hospital_comparison(db: Session, year: int, month: int | None) -> list[HospitalRow]:
    hospitals = list(db.execute(select(Hospital).where(Hospital.deleted_at.is_(None))).scalars().all())
    gov_names = _governorate_names(db)
    rows: list[HospitalRow] = []
    for h in hospitals:
        summary = hospital_summary(db, h.id, year, month)
        rows.append(
            HospitalRow(
                hospital_id=h.id,
                hospital_name_ar=h.name_ar,
                governorate_name_ar=gov_names.get(h.governorate_id),
                reported=summary.period_status in REPORTED_STATUSES,
                period_status=summary.period_status,
                last_sync_label=_period_label(summary.period_id, summary.period_status),
                indicators_with_value=summary.indicators_with_value,
                indicators_met=summary.indicators_met,
                indicators_at_risk=summary.indicators_at_risk,
                compliance_percent=summary.compliance_percent,
                rows=summary.points,
            )
        )
    return sorted(rows, key=lambda x: (x.compliance_percent is None, -(x.compliance_percent or 0)))


def late_hospitals(db: Session, year: int, month: int | None) -> list[dict]:
    """Hospitals that have not submitted a period for the given month."""
    hospitals = list(db.execute(select(Hospital).where(Hospital.deleted_at.is_(None))).scalars().all())
    gov_names = _governorate_names(db)
    late: list[dict] = []
    for h in hospitals:
        period = _latest_period(db, h.id, year, month)
        status = period.status if period else None
        if status in REPORTED_STATUSES:
            continue
        late.append(
            {
                "hospital_id": h.id,
                "hospital_name_ar": h.name_ar,
                "governorate_name_ar": gov_names.get(h.governorate_id),
                "period_status": status or "no_period",
                "status_label_ar": _status_label(status),
            }
        )
    return late


def _status_label(status: str | None) -> str:
    labels = {
        None: "لم تُنشأ فترة",
        "no_period": "لم تُنشأ فترة",
        "draft": "مسودة لم تُرسل",
        "returned": "مُعادة للتعديل",
        "submitted": "مُرسلة",
        "reviewed": "مراجَعة",
        "approved": "معتمدة",
    }
    return labels.get(status, "—")


def report_rows(
    db: Session,
    year: int,
    month: int | None,
    hospital_id: uuid.UUID | None = None,
) -> list[dict]:
    """Flat rows for tabular exports: one row per (hospital, indicator, dept)."""
    if hospital_id is not None:
        hospitals = [db.get(Hospital, hospital_id)]
        hospitals = [h for h in hospitals if h is not None and h.deleted_at is None]
    else:
        hospitals = list(db.execute(select(Hospital).where(Hospital.deleted_at.is_(None))).scalars().all())

    gov_names = _governorate_names(db)
    out: list[dict] = []
    for h in hospitals:
        summary = hospital_summary(db, h.id, year, month)
        for p in summary.points:
            out.append(
                {
                    "hospital_name_ar": h.name_ar,
                    "governorate_name_ar": gov_names.get(h.governorate_id) or "—",
                    "indicator_code": p.code,
                    "indicator_name_ar": p.name_ar,
                    "department_name_ar": p.department_name_ar or "على مستوى المستشفى",
                    "value": p.value,
                    "unit_ar": p.unit_ar or "",
                    "target_value": p.target_value,
                    "assessment_label_ar": p.assessment_label_ar,
                    "movement_label_ar": _movement_label(p.movement, p.improving),
                }
            )
    return out


def _movement_label(movement: str, improving: bool | None) -> str:
    if movement == "unknown":
        return "لا مقارنة"
    if movement == "flat":
        return "مستقر"
    if improving is True:
        return "تحسّن"
    if improving is False:
        return "تراجع"
    return "ارتفاع" if movement == "up" else "انخفاض"


def generated_at_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_value(value: object) -> str:
    """Human-readable number for reports (em dash when there is no value)."""
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)
