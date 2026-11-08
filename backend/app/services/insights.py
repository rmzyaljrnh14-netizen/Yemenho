"""Deterministic insight engine (v0.8).

The national assistant must never invent a number, a cause or a medical
judgement. So the analytical core is plain, auditable arithmetic over stored
rows: trends, statistical anomalies, late submissions and improvement areas.
Every finding carries the numbers it was computed from, so a person can check it
by hand.

The optional language model (see ``ai_narrator``) only *narrates* these findings;
it never sees raw data and can never add a fact. When no model is configured the
assistant still works fully — it just returns the computed findings.

Honesty rules (same spirit as the calculation engine):
  * a missing value is ``None``, never counted as zero;
  * a series with too few points yields "insufficient data", not a guess;
  * a flat series yields "stable", not a fake rise or fall;
  * every response carries a disclaimer that this is an automated aid, not a
    medical or administrative ruling.
"""
from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.core import (
    CapaAction,
    ConflictLog,
    Hospital,
    Incident,
    Indicator,
    IndicatorValue,
    QualityAudit,
    ReportingPeriod,
    Risk,
    SyncNode,
)
from app.services import analytics
from app.services import alert_rules
from app.services.indicators import trend_is_improving

DISCLAIMER_AR = (
    "هذا تحليل آلي مساعد مبني على البيانات المسجّلة فقط، وليس حكماً طبياً ولا إدارياً. "
    "كل نتيجة مرفقة بالأرقام التي حُسبت منها، ويجب أن يراجعها مختص قبل أي قرار."
)

# Minimum points before we dare talk about a trend or an anomaly.
MIN_POINTS_TREND = 3
MIN_POINTS_ANOMALY = 4
# Modified z-score threshold (Iglewicz & Hoaglin): |z| >= 3.5 is a likely outlier.
ANOMALY_Z = 3.5

DIRECTION_LABEL_AR = {
    "higher_better": "الارتفاع أفضل",
    "lower_better": "الانخفاض أفضل",
    "target_range": "الالتزام بنطاق مستهدف",
}

MONTHS_AR = (
    "", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)


def period_label_ar(year: int, month: int | None) -> str:
    """A readable Arabic period label, e.g. 'أكتوبر 2026' or 'سنة 2026'."""
    if month and 1 <= month <= 12:
        return f"{MONTHS_AR[month]} {year}"
    return f"سنة {year}"


# ---------------------------------------------------------------------------
# Pure statistics (no database): easy to test and to trust.
# ---------------------------------------------------------------------------
def linear_slope(values: list[float]) -> float | None:
    """Least-squares slope of a series against its index (x = 0, 1, 2, ...).

    Returns None when there are fewer than two points. A flat series returns 0.0.
    """
    n = len(values)
    if n < 2:
        return None
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    numer = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    return numer / denom


def detect_anomaly(
    values: list[float],
    z_threshold: float = ANOMALY_Z,
    min_points: int = MIN_POINTS_ANOMALY,
) -> dict:
    """Flag whether the last point is a statistical outlier of its own history.

    Uses the modified z-score (median + MAD), which is robust to a few outliers
    and needs no assumption of normality. It reports the score and the basis; it
    never claims a cause. The threshold and the minimum number of points come
    from the configurable alert rules (v0.10).
    """
    if len(values) < min_points:
        return {
            "is_anomaly": False,
            "reason": "insufficient_data",
            "needed": min_points,
            "have": len(values),
        }
    history = values[:-1]
    latest = values[-1]
    median = statistics.median(history)
    deviations = [abs(v - median) for v in history]
    mad = statistics.median(deviations)
    if mad == 0.0:
        # Every historical point sits on the median: only a change away from it
        # is notable, and a robust scale is undefined, so we cannot score it.
        if latest == median:
            return {"is_anomaly": False, "reason": "flat_history", "median": median, "latest": latest}
        return {
            "is_anomaly": True,
            "reason": "deviation_from_flat_history",
            "median": median,
            "latest": latest,
            "modified_z": None,
        }
    z = 0.6745 * (latest - median) / mad
    return {
        "is_anomaly": abs(z) >= z_threshold,
        "reason": "modified_z_score",
        "modified_z": round(z, 2),
        "threshold": z_threshold,
        "median": round(median, 4),
        "mad": round(mad, 4),
        "latest": latest,
    }


def direction_of_slope(slope: float | None, scale: float) -> str:
    """Turn a slope into 'up' | 'down' | 'flat' | 'unknown'.

    ``scale`` is a sensible reference (e.g. the series mean) so a tiny slope on a
    large series is not mistaken for a real move.
    """
    if slope is None:
        return "unknown"
    if scale <= 0:
        scale = 1.0
    if abs(slope) <= 0.02 * scale:
        return "flat"
    return "up" if slope > 0 else "down"


# ---------------------------------------------------------------------------
# DB-backed insight builders
# ---------------------------------------------------------------------------
@dataclass
class Insight:
    kind: str
    severity: str  # "high" | "medium" | "info"
    title_ar: str
    detail_ar: str
    basis: dict = field(default_factory=dict)
    hospital_id: uuid.UUID | None = None
    indicator_id: uuid.UUID | None = None


def _values_for_indicator(
    db: Session, indicator_id: uuid.UUID, hospital_id: uuid.UUID, limit: int = 12
) -> list[tuple[ReportingPeriod, float]]:
    """Monthly (period, value) pairs for one indicator in one hospital, oldest first."""
    rows = db.execute(
        select(ReportingPeriod, IndicatorValue.value)
        .join(IndicatorValue, IndicatorValue.period_id == ReportingPeriod.id)
        .where(
            ReportingPeriod.hospital_id == hospital_id,
            ReportingPeriod.period_type == "monthly",
            ReportingPeriod.deleted_at.is_(None),
            IndicatorValue.indicator_id == indicator_id,
            IndicatorValue.department_id.is_(None),
            IndicatorValue.deleted_at.is_(None),
            IndicatorValue.value.isnot(None),
        )
        .order_by(ReportingPeriod.year.desc(), ReportingPeriod.month.desc().nullslast())
        .limit(limit)
    ).all()
    pairs = [(p, float(v)) for p, v in rows]
    pairs.reverse()
    return pairs


def indicator_trend_insights(
    db: Session, hospital_id: uuid.UUID, hospital_name: str
) -> list[Insight]:
    """Trend and anomaly findings for every indicator that has enough history.

    Thresholds come from the configurable alert rules (v0.10) resolved for this
    hospital; a disabled rule suppresses that kind of finding for the hospital.
    """
    rules = alert_rules.load_rules(db, hospital_id)
    trend_rule = rules["trend"]
    anom_rule = rules["anomaly"]
    trend_min = int(trend_rule.params.get("min_points", MIN_POINTS_TREND))
    anom_min = int(anom_rule.params.get("min_points", MIN_POINTS_ANOMALY))
    anom_z = float(anom_rule.params.get("z_threshold", ANOMALY_Z))

    indicators = list(
        db.execute(select(Indicator).where(Indicator.deleted_at.is_(None)).order_by(Indicator.code)).scalars()
    )
    out: list[Insight] = []
    for ind in indicators:
        pairs = _values_for_indicator(db, ind.id, hospital_id)
        if len(pairs) < min(trend_min, anom_min):
            continue
        values = [v for _, v in pairs]
        labels = [analytics._month_label(p.year, p.month) for p, _ in pairs]
        slope = linear_slope(values)
        scale = abs(sum(values) / len(values))
        movement = direction_of_slope(slope, scale)
        improving = trend_is_improving(movement, ind.direction)
        if trend_rule.enabled and len(pairs) >= trend_min and movement in ("up", "down"):
            out.append(
                Insight(
                    kind="trend",
                    severity="medium" if improving is False else "info",
                    title_ar=f"{ind.name_ar}: اتجاه {'ارتفاع' if movement == 'up' else 'انخفاض'}",
                    detail_ar=(
                        f"من {labels[0]} إلى {labels[-1]} تغيّرت القيمة من "
                        f"{_fmt(values[0])} إلى {_fmt(values[-1])}. "
                        f"اتجاه التحسن لهذا المؤشر: {DIRECTION_LABEL_AR.get(ind.direction, 'غير معرّف')}."
                    ),
                    basis={
                        "indicator_code": ind.code,
                        "unit_ar": ind.unit_ar,
                        "series": [
                            {"period": labels[i], "value": values[i]} for i in range(len(values))
                        ],
                        "slope_per_period": round(slope, 6) if slope is not None else None,
                        "movement": movement,
                        "improving": improving,
                        "direction": ind.direction,
                    },
                    hospital_id=hospital_id,
                    indicator_id=ind.id,
                )
            )
        anom = detect_anomaly(values, z_threshold=anom_z, min_points=anom_min)
        if anom_rule.enabled and anom.get("is_anomaly"):
            out.append(
                Insight(
                    kind="anomaly",
                    severity="high",
                    title_ar=f"{ind.name_ar}: قيمة غير معتادة في {labels[-1]}",
                    detail_ar=(
                        f"القيمة {_fmt(values[-1])} في {labels[-1]} تبتعد عن وسيط تاريخ المؤشر "
                        f"({_fmt(anom.get('median'))}) بمقدار يجاوز العتبة الإحصائية. "
                        "يُنصح بالتحقق من صحة البيانات قبل اعتبارها تغيّراً حقيقياً."
                    ),
                    basis={
                        "indicator_code": ind.code,
                        "unit_ar": ind.unit_ar,
                        "series": [
                            {"period": labels[i], "value": values[i]} for i in range(len(values))
                        ],
                        "latest_period": labels[-1],
                        "latest_value": values[-1],
                        "detection": anom,
                    },
                    hospital_id=hospital_id,
                    indicator_id=ind.id,
                )
            )
    return out


def late_submission_insights(db: Session, year: int, month: int | None) -> list[Insight]:
    """Hospitals that have not sent their period, plus open RCA/CAPA/risk pressure.

    This kind is a national on/off switch (v0.10): the default is on, and an
    operator may turn it off so the alert centre stops showing late submissions.
    """
    if not alert_rules.is_enabled(db, "late_submission", None):
        return []
    out: list[Insight] = []
    for row in analytics.late_hospitals(db, year, month):
        out.append(
            Insight(
                kind="late_submission",
                severity="high",
                title_ar=f"{row['hospital_name_ar']} — لم تُرسل بيانات الفترة",
                detail_ar=f"الحالة: {row['status_label_ar']} ({period_label_ar(year, month)}).",
                basis={"period_status": row["period_status"], "year": year, "month": month},
                hospital_id=row["hospital_id"],
            )
        )
    return out


def quality_pressure_insights(db: Session) -> list[Insight]:
    """Open incidents, overdue corrective actions and high risks, from real rows.

    Every threshold (risk score, CAPA grace days, minimum counts) is resolved per
    hospital from the configurable alert rules (v0.10).
    """
    out: list[Insight] = []
    today = datetime.now(timezone.utc).date()

    # Resolve the rule set for every hospital that has any pressure row, in one
    # pass, so a per-hospital override is honoured without an extra query each.
    hosp_ids: set[uuid.UUID] = set()
    for model in (CapaAction, Risk, Incident):
        hosp_ids.update(
            r[0]
            for r in db.execute(
                select(model.hospital_id).where(model.deleted_at.is_(None)).distinct()
            ).all()
        )
    rules_by_hospital = {hid: alert_rules.load_rules(db, hid) for hid in hosp_ids}

    def _rule(hid: uuid.UUID, kind: str):
        return rules_by_hospital.get(hid, {}).get(kind)

    capa_rows = db.execute(
        select(CapaAction.hospital_id, CapaAction.due_date)
        .where(
            CapaAction.deleted_at.is_(None),
            CapaAction.status.notin_(("done", "verified", "cancelled")),
            CapaAction.due_date.isnot(None),
        )
    ).all()
    overdue_counts: dict[uuid.UUID, int] = {}
    for hospital_id, due_date in capa_rows:
        rule = _rule(hospital_id, "overdue_capa")
        if rule is None or not rule.enabled:
            continue
        grace = int(rule.params.get("grace_days", 0))
        if due_date is not None and due_date < today - timedelta(days=grace):
            overdue_counts[hospital_id] = overdue_counts.get(hospital_id, 0) + 1
    for hospital_id, count in overdue_counts.items():
        rule = _rule(hospital_id, "overdue_capa")
        out.append(
            Insight(
                kind="overdue_capa",
                severity="high",
                title_ar="إجراءات تصحيحية ووقائية متأخرة عن موعدها",
                detail_ar=f"يوجد {count} إجراء تجاوز تاريخ الاستحقاق ولم يُنفَّذ بعد.",
                basis={"overdue_count": count, "as_of": today.isoformat()},
                hospital_id=hospital_id,
            )
        )

    high_risks = db.execute(
        select(Risk.hospital_id, func.count())
        .where(Risk.deleted_at.is_(None), Risk.status == "open")
        .group_by(Risk.hospital_id)
    ).all()
    for hospital_id, _total in high_risks:
        rule = _rule(hospital_id, "high_risk")
        if rule is None or not rule.enabled:
            continue
        threshold = int(rule.params.get("score_threshold", 15))
        count = db.execute(
            select(func.count())
            .select_from(Risk)
            .where(
                Risk.hospital_id == hospital_id,
                Risk.deleted_at.is_(None),
                Risk.status == "open",
                Risk.score >= threshold,
            )
        ).scalar_one()
        if count <= 0:
            continue
        out.append(
            Insight(
                kind="high_risk",
                severity="high",
                title_ar="مخاطر عالية مفتوحة",
                detail_ar=f"يوجد {int(count)} خطر بدرجة {threshold} أو أكثر ولا يزال مفتوحاً.",
                basis={"high_risk_count": int(count), "score_threshold": threshold},
                hospital_id=hospital_id,
            )
        )

    open_incidents = db.execute(
        select(Incident.hospital_id, func.count())
        .where(Incident.deleted_at.is_(None), Incident.status.notin_(("closed", "rejected")))
        .group_by(Incident.hospital_id)
    ).all()
    for hospital_id, count in open_incidents:
        rule = _rule(hospital_id, "open_incidents")
        if rule is None or not rule.enabled:
            continue
        minimum = int(rule.params.get("min_count", 1))
        if int(count) < minimum:
            continue
        out.append(
            Insight(
                kind="open_incidents",
                severity="medium",
                title_ar="حوادث مفتوحة بانتظار المعالجة",
                detail_ar=f"يوجد {int(count)} حادث لم يُغلق بعد.",
                basis={"open_incident_count": int(count), "min_count": minimum},
                hospital_id=hospital_id,
            )
        )

    open_rca = db.execute(
        select(Incident.hospital_id, func.count())
        .select_from(Incident)
        .where(Incident.deleted_at.is_(None), Incident.status == "rca")
        .group_by(Incident.hospital_id)
    ).all()
    for hospital_id, count in open_rca:
        rule = _rule(hospital_id, "open_rca")
        if rule is None or not rule.enabled:
            continue
        minimum = int(rule.params.get("min_count", 1))
        if int(count) < minimum:
            continue
        out.append(
            Insight(
                kind="open_rca",
                severity="medium",
                title_ar="تحليلات أسباب جذرية قيد العمل",
                detail_ar=f"يوجد {int(count)} حادث في مرحلة تحليل الأسباب الجذرية.",
                basis={"open_rca_count": int(count), "min_count": minimum},
                hospital_id=hospital_id,
            )
        )
    return out


def sync_health_insights(db: Session) -> list[Insight]:
    """Sync health findings: stale devices and unreviewed conflicts (v0.13).

    Both come from real rows the sync engine already writes — ``sync_nodes`` for
    device freshness and ``conflict_log`` for edits that collided. Nothing is
    invented: a device with no ``last_seen_at`` or one older than the threshold
    is late, and a conflict whose resolution is still ``auto_server`` is open.
    The thresholds are resolved per hospital from the configurable alert rules.
    """
    out: list[Insight] = []
    now = datetime.now(timezone.utc)

    nodes = list(db.execute(select(SyncNode)).scalars().all())
    # Resolve each hospital's rule once.
    node_hospitals = {n.hospital_id for n in nodes if n.hospital_id is not None}
    rules_by_hospital = {hid: alert_rules.load_rules(db, hid) for hid in node_hospitals}

    for node in nodes:
        if node.hospital_id is None:
            continue
        rule = rules_by_hospital.get(node.hospital_id, {}).get("stale_device")
        if rule is None or not rule.enabled:
            continue
        stale_days = int(rule.params.get("stale_days", 7))
        seen = node.last_seen_at
        if seen is not None:
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            days = (now - seen).total_seconds() / 86400.0
            if days < stale_days:
                continue
            age_label = f"{int(days)} يوماً"
        else:
            age_label = "أبداً"
        out.append(
            Insight(
                kind="stale_device",
                severity="high",
                title_ar="جهاز مزامنة متأخر عن الإرسال",
                detail_ar=(
                    f"لم يُزامن الجهاز «{node.name or node.node_id}» منذ {age_label} "
                    f"(عتبة {stale_days} يوماً)."
                ),
                basis={
                    "node_id": node.node_id,
                    "last_seen_at": seen.isoformat() if seen else None,
                    "stale_days": stale_days,
                    "days_since_seen": int(days) if seen else None,
                },
                hospital_id=node.hospital_id,
            )
        )

    open_conflicts = db.execute(
        select(ConflictLog.hospital_id, func.count())
        .where(
            ConflictLog.resolution == "auto_server",
            ConflictLog.hospital_id.isnot(None),
        )
        .group_by(ConflictLog.hospital_id)
    ).all()
    for hospital_id, count in open_conflicts:
        rule = alert_rules.load_rules(db, hospital_id).get("open_conflict")
        if rule is None or not rule.enabled:
            continue
        minimum = int(rule.params.get("min_count", 1))
        if int(count) < minimum:
            continue
        out.append(
            Insight(
                kind="open_conflict",
                severity="high",
                title_ar="تعارضات مزامنة بانتظار المراجعة",
                detail_ar=f"يوجد {int(count)} تعارض مزامنة لم يراجعه مسؤول بعد.",
                basis={"open_conflict_count": int(count), "min_count": minimum},
                hospital_id=hospital_id,
            )
        )
    return out


def improvement_areas(db: Session, hospital_id: uuid.UUID, year: int, month: int | None) -> list[dict]:
    """Indicators below target, as concrete candidate areas for improvement."""
    summary = analytics.hospital_summary(db, hospital_id, year, month)
    areas: list[dict] = []
    for p in summary.points:
        if p.value is None:
            continue
        if p.assessment_status in ("warning", "poor"):
            areas.append(
                {
                    "indicator_code": p.code,
                    "indicator_name_ar": p.name_ar,
                    "department_name_ar": p.department_name_ar,
                    "value": p.value,
                    "unit_ar": p.unit_ar,
                    "target_value": p.target_value,
                    "assessment_status": p.assessment_status,
                    "assessment_label_ar": p.assessment_label_ar,
                    "movement": p.movement,
                }
            )
    # Worst first: poor before warning, then by distance from target.
    def rank(a: dict) -> tuple:
        return (a["assessment_status"] != "poor", a["indicator_code"])

    areas.sort(key=rank)
    return areas


def hospital_insight_bundle(
    db: Session, hospital_id: uuid.UUID, year: int, month: int | None
) -> dict:
    """Everything the assistant can honestly say about one hospital for a period."""
    hospital = db.get(Hospital, hospital_id)
    name = hospital.name_ar if hospital else "—"
    summary = analytics.hospital_summary(db, hospital_id, year, month)
    insights = indicator_trend_insights(db, hospital_id, name)
    # Only keep quality-pressure findings for this hospital.
    insights += [
        i
        for i in quality_pressure_insights(db)
        if i.hospital_id is None or i.hospital_id == hospital_id
    ]
    # Sync-health findings (stale device / open conflict) for this hospital.
    insights += [i for i in sync_health_insights(db) if i.hospital_id == hospital_id]
    insights.sort(key=lambda i: {"high": 0, "medium": 1, "info": 2}[i.severity])
    return {
        "hospital_id": hospital_id,
        "hospital_name_ar": name,
        "year": year,
        "month": month,
        "period_status": summary.period_status,
        "compliance_percent": summary.compliance_percent,
        "indicators_with_value": summary.indicators_with_value,
        "indicators_met": summary.indicators_met,
        "indicators_at_risk": summary.indicators_at_risk,
        "insights": [i.__dict__ for i in insights],
        "improvement_areas": improvement_areas(db, hospital_id, year, month),
        "disclaimer_ar": DISCLAIMER_AR,
        "generated_at": _now(),
    }


def national_insight_bundle(db: Session, year: int, month: int | None) -> dict:
    """National view: late submissions, quality pressure and worst performers."""
    overview = analytics.national_overview(db, year, month)
    insights: list[Insight] = []
    insights += late_submission_insights(db, year, month)
    insights += quality_pressure_insights(db)

    # Performance findings derived from the overview rows (real numbers). The
    # thresholds come from the configurable alert rules (v0.10).
    for row in overview["hospitals"]:
        if not row["reported"] or row["compliance_percent"] is None:
            continue
        rule = alert_rules.load_rules(db, row["hospital_id"]).get("low_compliance")
        if rule is None or not rule.enabled:
            continue
        warn_below = int(rule.params.get("warn_below", 85))
        high_below = int(rule.params.get("high_below", 70))
        pct = row["compliance_percent"]
        if pct < warn_below:
            insights.append(
                Insight(
                    kind="low_compliance",
                    severity="high" if pct < high_below else "medium",
                    title_ar=f"{row['hospital_name_ar']} — نسبة تحقيق {pct}%",
                    detail_ar=(
                        f"مؤشرات محققة {row['indicators_met']} من {row['indicators_with_value']} "
                        f"قيمة مسجّلة (دون عتبة {warn_below}%)."
                    ),
                    basis={
                        "compliance_percent": pct,
                        "indicators_met": row["indicators_met"],
                        "indicators_with_value": row["indicators_with_value"],
                        "warn_below": warn_below,
                        "high_below": high_below,
                    },
                    hospital_id=row["hospital_id"],
                )
            )
    insights.sort(key=lambda i: {"high": 0, "medium": 1, "info": 2}[i.severity])
    return {
        "year": year,
        "month": month,
        "hospitals_total": overview["hospitals_total"],
        "hospitals_reported": overview["hospitals_reported"],
        "compliance_percent": overview["compliance_percent"],
        "insights": [i.__dict__ for i in insights],
        "disclaimer_ar": DISCLAIMER_AR,
        "generated_at": _now(),
    }


# ---------------------------------------------------------------------------
# Draft report (plain text, built only from the numbers above)
# ---------------------------------------------------------------------------
def build_hospital_report_text(db: Session, hospital_id: uuid.UUID, year: int, month: int | None) -> str:
    bundle = hospital_insight_bundle(db, hospital_id, year, month)
    lines: list[str] = []
    lines.append(f"مسودة تقرير أداء — {bundle['hospital_name_ar']}")
    lines.append(f"الفترة: {period_label_ar(year, month)}")
    lines.append("")
    lines.append("1) ملخص الأرقام")
    if bundle["indicators_with_value"]:
        lines.append(
            f"- مؤشرات مسجّلة: {bundle['indicators_with_value']}، "
            f"محققة للهدف: {bundle['indicators_met']}، "
            f"دون الهدف: {bundle['indicators_at_risk']}."
        )
        if bundle["compliance_percent"] is not None:
            lines.append(f"- نسبة تحقيق الأهداف: {bundle['compliance_percent']}%.")
    else:
        lines.append("- لا توجد قيم مسجّلة لهذه الفترة.")
    lines.append("")

    highs = [i for i in bundle["insights"] if i["severity"] == "high"]
    lines.append("2) نقاط تحتاج انتباهاً عاجلاً")
    if highs:
        for i in highs:
            lines.append(f"- {i['title_ar']}: {i['detail_ar']}")
    else:
        lines.append("- لا توجد نقاط عالية الخطورة في البيانات الحالية.")
    lines.append("")

    lines.append("3) مجالات مقترحة للتحسين")
    if bundle["improvement_areas"]:
        for a in bundle["improvement_areas"][:10]:
            target = f" (المستهدف: {_fmt(a['target_value'])})" if a["target_value"] is not None else ""
            lines.append(
                f"- {a['indicator_name_ar']} [{a['indicator_code']}]: "
                f"القيمة {_fmt(a['value'])}{target} — {a['assessment_label_ar']}."
            )
    else:
        lines.append("- لا توجد مؤشرات دون الهدف في البيانات الحالية.")
    lines.append("")

    lines.append("4) تنبيه")
    lines.append(f"- {DISCLAIMER_AR}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt(value: object | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
