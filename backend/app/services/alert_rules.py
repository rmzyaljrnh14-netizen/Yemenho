"""Configurable alert rules (v0.10).

The insight engine's numeric thresholds used to be constants in code. They are
now *data*: this module owns the catalogue of tunable parameters, validates and
clamps anything stored, and resolves the effective rule for a hospital.

Resolution order (later wins): code default -> national row (hospital_id NULL)
-> hospital override. A missing row simply means "use the default", so the
engine always has a value and a bad edit can never break it: every parameter is
clamped to a safe range and unknown keys are ignored.

Honesty is preserved: only thresholds are configurable. An alert is still
computed from real rows and never invented, and every alert keeps the numbers it
was derived from in its ``basis``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import AlertRule

# ---------------------------------------------------------------------------
# Catalogue of tunable parameters (typed table — data, not string matching)
# ---------------------------------------------------------------------------
# Defaults match the engine's original constants exactly.
DEFAULT_PARAMS: dict[str, dict] = {
    "low_compliance": {"warn_below": 85, "high_below": 70},
    "anomaly": {"z_threshold": 3.5, "min_points": 4},
    "trend": {"min_points": 3},
    "high_risk": {"score_threshold": 15},
    "overdue_capa": {"grace_days": 0},
    "open_incidents": {"min_count": 1},
    "open_rca": {"min_count": 1},
    # v0.13: sync health. A device unseen for >= stale_days is flagged; a single
    # open conflict flags the hospital. Both are national defaults by default.
    "stale_device": {"stale_days": 7},
    "open_conflict": {"min_count": 1},
    # No numeric threshold: a national on/off switch for late-submission alerts.
    "late_submission": {},
}

KIND_LABEL_AR: dict[str, str] = {
    "trend": "اتجاه المؤشر",
    "anomaly": "قيمة غير معتادة",
    "low_compliance": "تدنّي تحقيق الأهداف",
    "high_risk": "مخاطر عالية مفتوحة",
    "overdue_capa": "إجراءات تصحيحية متأخرة",
    "open_incidents": "حوادث مفتوحة",
    "open_rca": "تحليلات أسباب جذرية مفتوحة",
    "stale_device": "جهاز مزامنة متأخر",
    "open_conflict": "تعارضات مزامنة مفتوحة",
    "late_submission": "تأخر الإرسال",
}

KIND_DESCRIPTION_AR: dict[str, str] = {
    "trend": "ينبّه عند وجود اتجاه صاعد أو هابط في سلسلة قيم مؤشر بدرجة كافية.",
    "anomaly": "ينبّه عند قيمة أخيرة تبتعد إحصائياً عن تاريخ المؤشر.",
    "low_compliance": "ينبّه عند تدنّي نسبة تحقيق أهداف المستشفى عن العتبة.",
    "high_risk": "ينبّه عند وجود خطر مفتوح بدرجة تساوي العتبة أو تزيد.",
    "overdue_capa": "ينبّه عند إجراء تصحيحي تجاوز موعده (+ أيام سماح).",
    "open_incidents": "ينبّه عند بلوغ عدد الحوادث غير المغلقة الحد الأدنى.",
    "open_rca": "ينبّه عند وجود تحليلات أسباب جذرية قيد العمل.",
    "stale_device": "ينبّه عند عدم مزامنة جهاز المستشفى منذ عدد أيام يبلغ العتبة.",
    "open_conflict": "ينبّه عند وجود تعارضات مزامنة مفتوحة (لم يراجعها مسؤول بعد).",
    "late_submission": "ينبّه عند عدم إرسال المستشفى بيانات الفترة.",
}

# Which scope a rule may be set at. "national" = default only; "both" = default
# plus a per-hospital override.
APPLIES_TO: dict[str, str] = {
    "late_submission": "national",
    "trend": "both",
    "anomaly": "both",
    "low_compliance": "both",
    "high_risk": "both",
    "overdue_capa": "both",
    "open_incidents": "both",
    "open_rca": "both",
    "stale_device": "both",
    "open_conflict": "both",
}


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label_ar: str
    kind: str  # "int" | "float"
    minimum: float
    maximum: float
    step: float
    unit_ar: str = ""


PARAM_SPECS: dict[str, dict[str, ParamSpec]] = {
    "low_compliance": {
        "warn_below": ParamSpec("warn_below", "عتبة التنبيه (%)", "int", 0, 100, 1, "%"),
        "high_below": ParamSpec("high_below", "عتبة الخطورة العالية (%)", "int", 0, 100, 1, "%"),
    },
    "anomaly": {
        "z_threshold": ParamSpec("z_threshold", "عتبة الشذوذ الإحصائي (z)", "float", 1.0, 10.0, 0.1),
        "min_points": ParamSpec("min_points", "أقل عدد نقاط", "int", 3, 24, 1),
    },
    "trend": {
        "min_points": ParamSpec("min_points", "أقل عدد نقاط للاتجاه", "int", 2, 24, 1),
    },
    "high_risk": {
        "score_threshold": ParamSpec("score_threshold", "أقل درجة خطر", "int", 1, 25, 1),
    },
    "overdue_capa": {
        "grace_days": ParamSpec("grace_days", "أيام سماح بعد الاستحقاق", "int", 0, 90, 1, "يوم"),
    },
    "open_incidents": {
        "min_count": ParamSpec("min_count", "أقل عدد حوادث مفتوحة", "int", 1, 100, 1),
    },
    "open_rca": {
        "min_count": ParamSpec("min_count", "أقل عدد تحليلات مفتوحة", "int", 1, 100, 1),
    },
    "stale_device": {
        "stale_days": ParamSpec("stale_days", "أيام التأخر قبل التنبيه", "int", 1, 90, 1, "يوم"),
    },
    "open_conflict": {
        "min_count": ParamSpec("min_count", "أقل عدد تعارضات مفتوحة", "int", 1, 100, 1),
    },
}

# Kinds a caller may configure (everything with at least one parameter).
CONFIGURABLE_KINDS: tuple[str, ...] = tuple(DEFAULT_PARAMS.keys())


def _coerce(spec: ParamSpec, value) -> float | None:
    try:
        if spec.kind == "int":
            return float(int(round(float(value))))
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp_params(kind: str, params: dict | None) -> dict:
    """Return a clean, in-range parameter set for ``kind``.

    Unknown keys are dropped and out-of-range values are clamped, so anything a
    caller stores can always be read back safely by the engine.
    """
    defaults = dict(DEFAULT_PARAMS.get(kind, {}))
    spec = PARAM_SPECS.get(kind, {})
    out = dict(defaults)
    for key, raw in (params or {}).items():
        s = spec.get(key)
        if s is None:
            continue
        v = _coerce(s, raw)
        if v is None:
            continue
        out[key] = int(v) if s.kind == "int" else v
        out[key] = min(max(out[key], s.minimum), s.maximum)
        if s.kind == "int":
            out[key] = int(out[key])
    # Cross-field sanity: the "high" threshold can never sit above the "warn" one.
    if kind == "low_compliance" and out.get("high_below", 0) > out.get("warn_below", 100):
        out["high_below"] = out["warn_below"]
    return out


@dataclass
class EffectiveRule:
    kind: str
    params: dict
    enabled: bool
    hospital_override: bool


def load_rules(db: Session, hospital_id: uuid.UUID | None) -> dict[str, EffectiveRule]:
    """Resolve the effective rule for every kind in one pass.

    Row-level security already limits the rows to the national defaults plus the
    hospitals a caller may see; we additionally keep only the national row and
    the requested hospital's row.
    """
    rows = list(
        db.execute(select(AlertRule).where(AlertRule.deleted_at.is_(None))).scalars()
    )
    by_hospital_kind: dict[tuple[uuid.UUID | None, str], AlertRule] = {}
    for r in rows:
        by_hospital_kind[(r.hospital_id, r.kind)] = r

    out: dict[str, EffectiveRule] = {}
    for kind in DEFAULT_PARAMS:
        params = dict(DEFAULT_PARAMS[kind])
        enabled = True
        override = False
        nat = by_hospital_kind.get((None, kind))
        if nat is not None:
            params.update(nat.params or {})
            enabled = bool(nat.is_enabled)
        if hospital_id is not None:
            hos = by_hospital_kind.get((hospital_id, kind))
            if hos is not None:
                params.update(hos.params or {})
                enabled = bool(hos.is_enabled)
                override = True
        out[kind] = EffectiveRule(
            kind=kind, params=clamp_params(kind, params), enabled=enabled, hospital_override=override
        )
    return out


def params_for(db: Session, kind: str, hospital_id: uuid.UUID | None) -> dict:
    """Convenience: the effective parameters for a single kind."""
    rules = load_rules(db, hospital_id)
    rule = rules.get(kind)
    return dict(rule.params) if rule is not None else dict(DEFAULT_PARAMS.get(kind, {}))


def is_enabled(db: Session, kind: str, hospital_id: uuid.UUID | None) -> bool:
    rules = load_rules(db, hospital_id)
    rule = rules.get(kind)
    return bool(rule.enabled) if rule is not None else True


# ---------------------------------------------------------------------------
# Views for the API / UI
# ---------------------------------------------------------------------------
def _params_spec_out(kind: str) -> list[dict]:
    return [
        {
            "key": s.key,
            "label_ar": s.label_ar,
            "type": s.kind,
            "min": s.minimum,
            "max": s.maximum,
            "step": s.step,
            "unit_ar": s.unit_ar,
        }
        for s in PARAM_SPECS.get(kind, {}).values()
    ]


def catalogue(db: Session, hospital_id: uuid.UUID | None) -> list[dict]:
    """Every configurable kind with its effective, national and hospital values."""
    rows = list(
        db.execute(select(AlertRule).where(AlertRule.deleted_at.is_(None))).scalars()
    )
    nat_by_kind = {r.kind: r for r in rows if r.hospital_id is None}
    hos_by_kind = {r.kind: r for r in rows if hospital_id is not None and r.hospital_id == hospital_id}
    effective = load_rules(db, hospital_id)

    out: list[dict] = []
    for kind in CONFIGURABLE_KINDS:
        eff = effective[kind]
        nat = nat_by_kind.get(kind)
        hos = hos_by_kind.get(kind)
        out.append(
            {
                "kind": kind,
                "label_ar": KIND_LABEL_AR.get(kind, kind),
                "description_ar": KIND_DESCRIPTION_AR.get(kind, ""),
                "applies_to": APPLIES_TO.get(kind, "both"),
                "enabled": eff.enabled,
                "effective_params": eff.params,
                "national_params": clamp_params(kind, (nat.params if nat else DEFAULT_PARAMS[kind])),
                "hospital_params": clamp_params(kind, hos.params) if hos is not None else None,
                "hospital_override": eff.hospital_override,
                "params_spec": _params_spec_out(kind),
            }
        )
    return out


def upsert_rule(
    db: Session,
    *,
    kind: str,
    hospital_id: uuid.UUID | None,
    params: dict,
    is_enabled: bool,
    note_ar: str | None,
    user_id: uuid.UUID,
) -> AlertRule:
    """Create or update a rule row. Raises ValueError for an unknown kind/scope."""
    if kind not in CONFIGURABLE_KINDS:
        raise ValueError("unknown_kind")
    scope = APPLIES_TO.get(kind, "both")
    if hospital_id is not None and scope != "both":
        raise ValueError("not_overridable")

    clean = clamp_params(kind, params)
    row = db.execute(
        select(AlertRule).where(
            AlertRule.kind == kind,
            AlertRule.hospital_id.is_(None) if hospital_id is None else AlertRule.hospital_id == hospital_id,
            AlertRule.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        row = AlertRule(kind=kind, hospital_id=hospital_id)
        db.add(row)
    row.params = clean
    row.is_enabled = bool(is_enabled)
    row.note_ar = (note_ar or "").strip() or None
    row.updated_by = user_id
    db.commit()
    # No refresh: the commit drops the transaction-local RLS context, so reading
    # the row back would be filtered out. The caller re-reads the catalogue after
    # restoring the context.
    return row


def reset_rule(db: Session, *, kind: str, hospital_id: uuid.UUID | None) -> bool:
    """Remove an override so the next scope's value applies again.

    Soft-deletes the row (history is kept). Returns True when a live row was
    removed, False when there was nothing to reset.
    """
    from datetime import datetime, timezone

    row = db.execute(
        select(AlertRule).where(
            AlertRule.kind == kind,
            AlertRule.hospital_id.is_(None) if hospital_id is None else AlertRule.hospital_id == hospital_id,
            AlertRule.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return True
