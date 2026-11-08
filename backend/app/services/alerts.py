"""Unified alert centre (v0.9).

One place that answers: *what needs attention right now, and has anyone dealt
with it?* Every alert is computed on the fly from stored rows by the same
deterministic insight engine the assistant uses (``app/services/insights``), so
an alert can never drift from the data it describes and no alert is ever
invented.

What this module adds on top of the insight engine:

  * a **stable ``alert_key``** for each finding, so the same alert keeps its
    identity across recomputations and can be acknowledged once;
  * the **acknowledgement state** (who saw it, when, with what note), read from
    ``alert_acknowledgements`` — the only thing that is persisted;
  * a flat, filterable list plus honest counts by severity and kind.

The alert body is never stored: only the acknowledgement is. Reopen an alert by
soft-deleting its acknowledgement, so history is kept but the alert shows again.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import AlertAcknowledgement, Hospital
from app.services import insights
from app.services.identity import Identity

# Which area each alert kind belongs to, so the UI can group them.
KIND_SOURCE = {
    "trend": "indicators",
    "anomaly": "indicators",
    "low_compliance": "indicators",
    "late_submission": "submission",
    "overdue_capa": "quality",
    "high_risk": "quality",
    "open_incidents": "quality",
    "open_rca": "quality",
    "stale_device": "sync",
    "open_conflict": "sync",
}

SOURCE_LABEL_AR = {
    "indicators": "المؤشرات",
    "submission": "الإرسال",
    "quality": "الجودة وسلامة المرضى",
    "sync": "المزامنة",
}


@dataclass
class Alert:
    key: str
    kind: str
    source: str
    severity: str  # "high" | "medium" | "info"
    title_ar: str
    detail_ar: str
    hospital_id: uuid.UUID | None = None
    hospital_name_ar: str | None = None
    period_year: int = 0
    period_month: int | None = None
    basis: dict = field(default_factory=dict)
    acked: bool = False
    acked_by_name: str | None = None
    acked_at: str | None = None
    note_ar: str | None = None


def alert_key(
    kind: str,
    hospital_id: uuid.UUID | None,
    year: int,
    month: int | None,
    discriminator: str = "",
) -> str:
    """A short, stable, URL-safe key for one alert.

    Built from the finding's identity (kind, hospital, period and, when present,
    the indicator) and hashed so the key is opaque and free of separators that
    would confuse a URL.
    """
    raw = f"{kind}|{hospital_id or 'national'}|{year}|{month if month is not None else 'all'}|{discriminator}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return f"{kind}-{digest}"


def _hospital_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = db.execute(select(Hospital.id, Hospital.name_ar).where(Hospital.id.in_(ids))).all()
    return {r[0]: r[1] for r in rows}


def _from_insight(
    ins: insights.Insight, year: int, month: int | None, names: dict[uuid.UUID, str]
) -> Alert:
    discriminator = str(ins.indicator_id) if ins.indicator_id else ""
    source = KIND_SOURCE.get(ins.kind, "other")
    return Alert(
        key=alert_key(ins.kind, ins.hospital_id, year, month, discriminator),
        kind=ins.kind,
        source=source,
        severity=ins.severity,
        title_ar=ins.title_ar,
        detail_ar=ins.detail_ar,
        hospital_id=ins.hospital_id,
        hospital_name_ar=names.get(ins.hospital_id) if ins.hospital_id else None,
        period_year=year,
        period_month=month,
        basis=ins.basis,
    )


def _low_compliance_insights(db: Session, year: int, month: int | None) -> list[insights.Insight]:
    """Hospitals below the compliance threshold, from the real overview rows.

    The two thresholds come from the configurable alert rules (v0.10), resolved
    per hospital so an override is honoured.
    """
    from app.services import alert_rules, analytics

    overview = analytics.national_overview(db, year, month)
    out: list[insights.Insight] = []
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
            out.append(
                insights.Insight(
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
    return out


def _load_acknowledgements(db: Session) -> dict[str, AlertAcknowledgement]:
    """Live acknowledgements keyed by alert_key (RLS already scopes them)."""
    rows = db.execute(
        select(AlertAcknowledgement).where(AlertAcknowledgement.deleted_at.is_(None))
    ).scalars()
    return {a.alert_key: a for a in rows}


def _ack_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    from app.models.core import User

    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all()
    return {r[0]: r[1] for r in rows}


def build_alerts(
    db: Session,
    identity: Identity,
    year: int,
    month: int | None,
    hospital_id: uuid.UUID | None = None,
) -> list[Alert]:
    """Compute every alert the caller may see, with acknowledgement state merged.

    ``hospital_id`` limits the list to one hospital (used by a hospital user and
    by the hospital picker in the portal). Without it, a central user gets the
    national list.
    """
    raw: list[insights.Insight] = []
    if hospital_id is not None:
        bundle = insights.hospital_insight_bundle(db, hospital_id, year, month)
        raw += [insights.Insight(**i) for i in bundle["insights"]]
        raw += _low_compliance_insights(db, year, month)
        # Keep only findings that belong to this hospital.
        raw = [i for i in raw if i.hospital_id in (None, hospital_id)]
    else:
        raw += insights.late_submission_insights(db, year, month)
        raw += insights.quality_pressure_insights(db)
        raw += insights.sync_health_insights(db)
        raw += _low_compliance_insights(db, year, month)

    names = _hospital_names(db, {i.hospital_id for i in raw if i.hospital_id})
    alerts = [_from_insight(i, year, month, names) for i in raw]

    acks = _load_acknowledgements(db)
    ack_user_ids = {a.acknowledged_by for a in acks.values() if a.acknowledged_by}
    ack_names = _ack_names(db, ack_user_ids)

    for a in alerts:
        ack = acks.get(a.key)
        if ack is not None:
            a.acked = True
            a.acked_at = ack.acknowledged_at.isoformat() if ack.acknowledged_at else None
            a.note_ar = ack.note_ar
            if ack.acknowledged_by:
                a.acked_by_name = ack_names.get(ack.acknowledged_by)

    order = {"high": 0, "medium": 1, "info": 2}
    alerts.sort(key=lambda a: (order.get(a.severity, 3), a.hospital_name_ar or "", a.kind))
    return alerts


def summarise(alerts: list[Alert]) -> dict:
    return {
        "total": len(alerts),
        "high": sum(1 for a in alerts if a.severity == "high"),
        "medium": sum(1 for a in alerts if a.severity == "medium"),
        "info": sum(1 for a in alerts if a.severity == "info"),
        "unacknowledged": sum(1 for a in alerts if not a.acked),
        "by_source": {
            src: sum(1 for a in alerts if a.source == src) for src in SOURCE_LABEL_AR
        },
    }
