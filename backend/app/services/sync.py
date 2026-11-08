"""Offline sync engine (v0.6) — server side of the protocol in docs/14.

Responsibilities:
  * apply an operation idempotently (same op_id never applies twice);
  * reject a write whose base revision is stale, recording it in conflict_log
    instead of silently overwriting;
  * freeze approved periods — a node can never overwrite approved data;
  * append every accepted change to a monotonic change_log so nodes pull only
    what changed since their cursor.

National reference rows (the indicator library) carry hospital_id = NULL and are
visible to every node. Hospital-scoped rows are protected by row-level security.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.core import (
    CapaAction,
    ChangeLog,
    ConflictLog,
    Department,
    Hospital,
    ImprovementAction,
    ImprovementPlan,
    Incident,
    Indicator,
    IndicatorAssignment,
    IndicatorValue,
    IndicatorValueRevision,
    QualityAudit,
    ReportingPeriod,
    Risk,
    SyncIdempotency,
    SyncNode,
)
from app.db.context import apply_rls_context
from app.services.identity import Identity
from app.services.indicators import CalculationError, compute_value

# Entity types a node may push. Everything else is rejected: national reference
# data and identity stay server-authoritative (docs/14 §6.2).
PUSHABLE_ENTITIES = {
    "reporting_period",
    "indicator_value",
    "incident",
    "capa_action",
    "risk",
    "audit",
    "improvement_plan",
    "improvement_action",
}

# Incidents are hospital-scoped and carry free text; these are the fields a node
# may set. Codes, status transitions and who closed a case stay server-owned.
INCIDENT_TYPES = {
    "medication", "fall", "pressure_ulcer", "infection", "surgical",
    "diagnostic", "transfusion", "equipment", "behaviour", "other",
}
INCIDENT_SEVERITIES = {"near_miss", "minor", "moderate", "major", "catastrophic"}
INCIDENT_HARMS = {"none", "mild", "moderate", "severe", "death"}

# CAPA actions (v0.14): a hospital plans corrective/preventive work offline.
CAPA_KINDS = {"corrective", "preventive"}
CAPA_PRIORITIES = {"low", "medium", "high", "critical"}
# A node may report an action as open or in progress; marking it done or verified
# is a server-side sign-off (who completed and verified it stays authoritative).
CAPA_NODE_STATUSES = {"open", "in_progress"}

# Risks (v0.14): the register is edited at the hospital. The score is a generated
# column on the server, so a device never sends it.
RISK_CATEGORIES = {
    "clinical", "medication", "infection", "environment", "equipment",
    "staffing", "information", "security", "other",
}
RISK_NODE_STATUSES = {"open", "mitigated", "accepted"}

# Internal audits (v0.15): a hospital opens an audit offline and records its
# scope and auditor. The code and the score are server-owned; a node may set the
# plan/in-progress states only, never complete or close its own audit.
AUDIT_NODE_STATUSES = {"planned", "in_progress"}

# Improvement plans (v0.15): a hospital drafts a plan offline. The code is
# server-owned; a node may keep a plan draft/active, never complete or cancel it.
PLAN_NODE_STATUSES = {"draft", "active"}

# Improvement actions (v0.15): a step under a plan. A node may set open or
# in_progress; done/cancelled stay server-owned.
ACTION_NODE_STATUSES = {"open", "in_progress"}

LOCKED_STATUSES = {"submitted", "reviewed", "approved"}


def _apply_rls(db: Session, identity: Identity) -> None:
    """Re-apply the row-level-security context after a commit.

    apply_rls_context uses set_config(..., true), which is transaction-local, so
    a commit drops it. Each operation commits on its own (docs/14 §4.3), so the
    context must be restored before the next statement.
    """
    apply_rls_context(
        db,
        is_central=identity.is_central,
        hospital_id=str(identity.hospital_id) if identity.hospital_id else None,
        governorate_id=str(identity.governorate_id) if identity.governorate_id else None,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _date(value) -> str | None:
    """A date (or datetime) as an ISO ``YYYY-MM-DD`` string, or None."""
    if value is None:
        return None
    return value.isoformat()[:10]


def _num(value: Decimal | float | None) -> float | None:
    return float(value) if value is not None else None


def _uid(value: uuid.UUID | str | None) -> str | None:
    return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# Payload serialisation (full row state, JSON-safe)
# ---------------------------------------------------------------------------
def period_payload(period: ReportingPeriod) -> dict:
    return {
        "id": str(period.id),
        "hospital_id": str(period.hospital_id),
        "period_type": period.period_type,
        "year": period.year,
        "month": period.month,
        "quarter": period.quarter,
        "status": period.status,
        "note": period.note,
        "rev": period.rev,
        "updated_at": _iso(period.updated_at),
        "deleted_at": _iso(period.deleted_at),
    }


def value_payload(value: IndicatorValue) -> dict:
    return {
        "id": str(value.id),
        "period_id": str(value.period_id),
        "indicator_id": str(value.indicator_id),
        "department_id": _uid(value.department_id),
        "numerator": _num(value.numerator),
        "denominator": _num(value.denominator),
        "value": _num(value.value),
        "value_type": value.value_type,
        "note": value.note,
        "rev": value.rev,
        "updated_at": _iso(value.updated_at),
        "deleted_at": _iso(value.deleted_at),
    }


def incident_payload(incident: Incident) -> dict:
    return {
        "id": str(incident.id),
        "hospital_id": str(incident.hospital_id),
        "department_id": _uid(incident.department_id),
        "code": incident.code,
        "title": incident.title,
        "description": incident.description,
        "incident_type": incident.incident_type,
        "severity": incident.severity,
        "patient_harm": incident.patient_harm,
        "occurred_at": _iso(incident.occurred_at),
        "reported_at": _iso(incident.reported_at),
        "is_anonymous": incident.is_anonymous,
        "status": incident.status,
        "immediate_action": incident.immediate_action,
        "closed_at": _iso(incident.closed_at),
        "updated_at": _iso(incident.updated_at),
        "deleted_at": _iso(incident.deleted_at),
    }


def capa_payload(capa: CapaAction) -> dict:
    return {
        "id": str(capa.id),
        "hospital_id": str(capa.hospital_id),
        "department_id": _uid(capa.department_id),
        "incident_id": _uid(capa.incident_id),
        "rca_id": _uid(capa.rca_id),
        "audit_id": _uid(capa.audit_id),
        "kind": capa.kind,
        "title": capa.title,
        "description_ar": capa.description_ar,
        "owner_name_ar": capa.owner_name_ar,
        "due_date": _date(capa.due_date),
        "priority": capa.priority,
        "status": capa.status,
        "completion_note_ar": capa.completion_note_ar,
        "rev": capa.rev,
        "updated_at": _iso(capa.updated_at),
        "deleted_at": _iso(capa.deleted_at),
    }


def risk_payload(risk: Risk) -> dict:
    return {
        "id": str(risk.id),
        "hospital_id": str(risk.hospital_id),
        "department_id": _uid(risk.department_id),
        "code": risk.code,
        "title": risk.title,
        "description_ar": risk.description_ar,
        "category": risk.category,
        "likelihood": risk.likelihood,
        "impact": risk.impact,
        "score": risk.score,
        "mitigation_ar": risk.mitigation_ar,
        "owner_name_ar": risk.owner_name_ar,
        "review_date": _date(risk.review_date),
        "status": risk.status,
        "rev": risk.rev,
        "updated_at": _iso(risk.updated_at),
        "deleted_at": _iso(risk.deleted_at),
    }


def audit_payload(audit: QualityAudit) -> dict:
    return {
        "id": str(audit.id),
        "hospital_id": str(audit.hospital_id),
        "department_id": _uid(audit.department_id),
        "code": audit.code,
        "title": audit.title,
        "standard_ar": audit.standard_ar,
        "scope_ar": audit.scope_ar,
        "auditor_name_ar": audit.auditor_name_ar,
        "audit_date": _date(audit.audit_date),
        "status": audit.status,
        "score": _num(audit.score),
        "findings_ar": audit.findings_ar,
        "rev": audit.rev,
        "updated_at": _iso(audit.updated_at),
        "deleted_at": _iso(audit.deleted_at),
    }


def improvement_plan_payload(plan: ImprovementPlan) -> dict:
    return {
        "id": str(plan.id),
        "hospital_id": str(plan.hospital_id),
        "department_id": _uid(plan.department_id),
        "code": plan.code,
        "title": plan.title,
        "objective_ar": plan.objective_ar,
        "baseline_ar": plan.baseline_ar,
        "target_ar": plan.target_ar,
        "indicator_id": _uid(plan.indicator_id),
        "owner_name_ar": plan.owner_name_ar,
        "start_date": _date(plan.start_date),
        "due_date": _date(plan.due_date),
        "status": plan.status,
        "rev": plan.rev,
        "updated_at": _iso(plan.updated_at),
        "deleted_at": _iso(plan.deleted_at),
    }


def improvement_action_payload(action: ImprovementAction, *, hospital_id) -> dict:
    # The action row has no hospital_id of its own; it is scoped by its plan.
    return {
        "id": str(action.id),
        "plan_id": str(action.plan_id),
        "hospital_id": _uid(hospital_id),
        "title": action.title,
        "owner_name_ar": action.owner_name_ar,
        "due_date": _date(action.due_date),
        "status": action.status,
        "note_ar": action.note_ar,
        "rev": action.rev,
        "updated_at": _iso(action.updated_at),
        "deleted_at": _iso(action.deleted_at),
    }


# ---------------------------------------------------------------------------
# Change log
# ---------------------------------------------------------------------------
def record_change(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    op: str,
    rev: int,
    hospital_id: uuid.UUID | None,
    payload: dict | None,
) -> int:
    """Append a change and return its server_seq."""
    row = ChangeLog(
        entity_type=entity_type,
        entity_id=entity_id,
        op=op,
        rev=rev,
        hospital_id=hospital_id,
        payload=payload,
    )
    db.add(row)
    db.flush()
    return int(row.server_seq)


def current_seq(db: Session) -> int:
    return int(db.execute(select(func.coalesce(func.max(ChangeLog.server_seq), 0))).scalar_one())


# ---------------------------------------------------------------------------
# Operation application
# ---------------------------------------------------------------------------
def _reject(op_id: str, reason: str, message_ar: str) -> dict:
    return {"op_id": op_id, "status": "rejected", "reason": reason, "message_ar": message_ar}


def _conflict(
    db: Session,
    *,
    op_id: str,
    entity_type: str,
    entity_id: str,
    node_id: str,
    hospital_id: uuid.UUID | None,
    local_payload: dict,
    server_payload: dict,
    current_rev: int,
) -> dict:
    db.add(
        ConflictLog(
            entity_type=entity_type,
            entity_id=entity_id,
            node_id=node_id,
            hospital_id=hospital_id,
            local_payload=local_payload,
            server_payload=server_payload,
            resolution="auto_server",
        )
    )
    return {
        "op_id": op_id,
        "status": "conflict",
        "reason": "rev_stale",
        "current_rev": current_rev,
        "server_payload": server_payload,
        "message_ar": "نسخة السجل على الخادم أحدث؛ اعتُمدت نسخة الخادم وسُجّل التعارض.",
    }


def _apply_period(db: Session, identity: Identity, node_id: str, op: dict, hospital_id: uuid.UUID) -> dict:
    op_id = op["op_id"]
    payload = op.get("payload") or {}
    try:
        entity_uuid = uuid.UUID(op["entity_id"])
    except (ValueError, TypeError):
        return _reject(op_id, "bad_id", "معرّف السجل غير صالح.")

    existing = db.get(ReportingPeriod, entity_uuid)

    if op["op"] == "delete":
        if existing is None:
            return {"op_id": op_id, "status": "applied", "new_rev": 0}
        if existing.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
        if existing.status in LOCKED_STATUSES:
            return _reject(op_id, "already_locked", "لا يمكن حذف فترة مُرسلة أو معتمدة.")
        if op["base_rev"] != existing.rev:
            return _conflict(
                db, op_id=op_id, entity_type="reporting_period", entity_id=op["entity_id"],
                node_id=node_id, hospital_id=hospital_id, local_payload=payload,
                server_payload=period_payload(existing), current_rev=existing.rev,
            )
        existing.deleted_at = _now()
        existing.rev += 1
        seq = record_change(db, entity_type="reporting_period", entity_id=op["entity_id"],
                            op="delete", rev=existing.rev, hospital_id=hospital_id,
                            payload=period_payload(existing))
        return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}

    if existing is None:
        if op["base_rev"] not in (0,):
            return _reject(op_id, "not_found", "السجل غير موجود على الخادم.")
        period = ReportingPeriod(
            id=entity_uuid,
            hospital_id=hospital_id,
            period_type=str(payload.get("period_type") or "monthly"),
            year=int(payload.get("year") or 0),
            month=payload.get("month"),
            quarter=payload.get("quarter"),
            status="draft",  # a node never creates an already-submitted period
            note=payload.get("note"),
        )
        if period.year < 2000 or period.year > 2100:
            return _reject(op_id, "validation_failed", "السنة غير صالحة.")
        db.add(period)
        db.flush()
        seq = record_change(db, entity_type="reporting_period", entity_id=op["entity_id"],
                            op="upsert", rev=period.rev, hospital_id=hospital_id,
                            payload=period_payload(period))
        return {"op_id": op_id, "status": "applied", "new_rev": period.rev, "server_seq": seq}

    # existing, upsert
    if existing.hospital_id != hospital_id:
        return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
    if existing.status in LOCKED_STATUSES:
        return _reject(
            op_id, "already_approved",
            "الفترة مُرسلة أو معتمدة ولا تُعدَّل من الجهاز؛ أعدها إلى مسودة من الخادم أولاً.",
        )
    if op["base_rev"] != existing.rev:
        return _conflict(
            db, op_id=op_id, entity_type="reporting_period", entity_id=op["entity_id"],
            node_id=node_id, hospital_id=hospital_id, local_payload=payload,
            server_payload=period_payload(existing), current_rev=existing.rev,
        )
    existing.period_type = str(payload.get("period_type") or existing.period_type)
    existing.year = int(payload.get("year") or existing.year)
    existing.month = payload.get("month")
    existing.quarter = payload.get("quarter")
    existing.note = payload.get("note")
    existing.rev += 1
    existing.updated_at = _now()
    seq = record_change(db, entity_type="reporting_period", entity_id=op["entity_id"],
                        op="upsert", rev=existing.rev, hospital_id=hospital_id,
                        payload=period_payload(existing))
    return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}


def _apply_value(db: Session, identity: Identity, node_id: str, op: dict, hospital_id: uuid.UUID) -> dict:
    op_id = op["op_id"]
    payload = op.get("payload") or {}
    try:
        entity_uuid = uuid.UUID(op["entity_id"])
    except (ValueError, TypeError):
        return _reject(op_id, "bad_id", "معرّف السجل غير صالح.")

    existing = db.get(IndicatorValue, entity_uuid)

    if op["op"] == "delete":
        if existing is None:
            return {"op_id": op_id, "status": "applied", "new_rev": 0}
        period = db.get(ReportingPeriod, existing.period_id)
        if period is None or period.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
        if period.status in LOCKED_STATUSES:
            return _reject(op_id, "already_locked", "لا يمكن حذف قيمة في فترة مُرسلة أو معتمدة.")
        if op["base_rev"] != existing.rev:
            return _conflict(
                db, op_id=op_id, entity_type="indicator_value", entity_id=op["entity_id"],
                node_id=node_id, hospital_id=hospital_id, local_payload=payload,
                server_payload=value_payload(existing), current_rev=existing.rev,
            )
        existing.deleted_at = _now()
        existing.rev += 1
        seq = record_change(db, entity_type="indicator_value", entity_id=op["entity_id"],
                            op="delete", rev=existing.rev, hospital_id=hospital_id,
                            payload=value_payload(existing))
        return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}

    # Resolve the period and confirm it belongs to this hospital and is editable.
    try:
        period_id = uuid.UUID(str(payload.get("period_id")))
    except (ValueError, TypeError):
        return _reject(op_id, "validation_failed", "الفترة غير محددة في السجل.")
    period = db.get(ReportingPeriod, period_id)
    if period is None or period.hospital_id != hospital_id:
        return _reject(op_id, "forbidden", "الفترة لا تخصّ مستشفى هذا الجهاز.")
    if period.status in LOCKED_STATUSES:
        return _reject(op_id, "already_approved", "الفترة مُرسلة أو معتمدة ولا تُعدَّل من الجهاز.")

    # The indicator is national reference data: the server is authoritative.
    try:
        indicator_id = uuid.UUID(str(payload.get("indicator_id")))
    except (ValueError, TypeError):
        return _reject(op_id, "validation_failed", "المؤشر غير محدد في السجل.")
    indicator = db.get(Indicator, indicator_id)
    if indicator is None or indicator.deleted_at is not None:
        return _reject(op_id, "unknown_indicator", "المؤشر غير موجود في المكتبة الوطنية.")

    department_id = payload.get("department_id")
    department_uuid = uuid.UUID(department_id) if department_id else None

    # Recompute the value server-side; never trust a node-computed number.
    try:
        computed, value_type = compute_value(
            computation=indicator.computation,
            numerator=payload.get("numerator"),
            denominator=payload.get("denominator"),
            multiplier=float(indicator.multiplier) if indicator.multiplier is not None else 1,
            entered_value=payload.get("entered_value"),
        )
    except CalculationError:
        return _reject(op_id, "validation_failed", "طريقة حساب المؤشر غير مدعومة.")

    if existing is None:
        if op["base_rev"] not in (0,):
            return _reject(op_id, "not_found", "القيمة غير موجودة على الخادم.")
        value = IndicatorValue(
            id=entity_uuid,
            period_id=period_id,
            indicator_id=indicator_id,
            department_id=department_uuid,
            numerator=payload.get("numerator"),
            denominator=payload.get("denominator"),
            value=computed,
            value_type=value_type,
            note=payload.get("note"),
            created_by=identity.user.id,
        )
        db.add(value)
        db.flush()
        db.add(IndicatorValueRevision(value_id=value.id, action="create", new_value=computed,
                                      new_numerator=payload.get("numerator"),
                                      new_denominator=payload.get("denominator"),
                                      note=payload.get("note"), actor_user_id=identity.user.id))
        seq = record_change(db, entity_type="indicator_value", entity_id=op["entity_id"],
                            op="upsert", rev=value.rev, hospital_id=hospital_id,
                            payload=value_payload(value))
        return {"op_id": op_id, "status": "applied", "new_rev": value.rev, "server_seq": seq}

    if existing.period_id != period_id:
        return _reject(op_id, "forbidden", "القيمة لا تخصّ هذه الفترة.")
    if op["base_rev"] != existing.rev:
        return _conflict(
            db, op_id=op_id, entity_type="indicator_value", entity_id=op["entity_id"],
            node_id=node_id, hospital_id=hospital_id, local_payload=payload,
            server_payload=value_payload(existing), current_rev=existing.rev,
        )
    db.add(IndicatorValueRevision(value_id=existing.id, action="update",
                                  old_value=existing.value, new_value=computed,
                                  old_numerator=existing.numerator, new_numerator=payload.get("numerator"),
                                  old_denominator=existing.denominator, new_denominator=payload.get("denominator"),
                                  note=payload.get("note"), actor_user_id=identity.user.id))
    existing.numerator = payload.get("numerator")
    existing.denominator = payload.get("denominator")
    existing.value = computed
    existing.value_type = value_type
    existing.note = payload.get("note")
    existing.rev += 1
    existing.updated_at = _now()
    seq = record_change(db, entity_type="indicator_value", entity_id=op["entity_id"],
                        op="upsert", rev=existing.rev, hospital_id=hospital_id,
                        payload=value_payload(existing))
    return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}


def _next_incident_code(db: Session, hospital_id: uuid.UUID) -> str:
    """A per-hospital human reference (INC-2026-0007), never reused."""
    year = _now().year
    count = db.execute(
        select(func.count()).select_from(Incident).where(Incident.hospital_id == hospital_id)
    ).scalar_one()
    return f"INC-{year}-{int(count) + 1:04d}"


def _apply_incident(db: Session, identity: Identity, node_id: str, op: dict, hospital_id: uuid.UUID) -> dict:
    """Create or update a patient-safety incident reported from an offline node.

    The node owns the free text (title, description, type, severity, harm,
    immediate action). The server owns the human code, the reported time and the
    status, so a device can never move a case through the review workflow.
    """
    op_id = op["op_id"]
    payload = op.get("payload") or {}
    try:
        entity_uuid = uuid.UUID(op["entity_id"])
    except (ValueError, TypeError):
        return _reject(op_id, "bad_id", "معرّف السجل غير صالح.")

    existing = db.get(Incident, entity_uuid)

    if op["op"] == "delete":
        if existing is None:
            return {"op_id": op_id, "status": "applied", "new_rev": 0}
        if existing.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
        if existing.status == "closed":
            return _reject(op_id, "already_locked", "لا يمكن حذف حادث مغلق.")
        if op["base_rev"] != existing.rev:
            return _conflict(
                db, op_id=op_id, entity_type="incident", entity_id=op["entity_id"],
                node_id=node_id, hospital_id=hospital_id, local_payload=payload,
                server_payload=incident_payload(existing), current_rev=existing.rev,
            )
        existing.deleted_at = _now()
        existing.rev += 1
        seq = record_change(db, entity_type="incident", entity_id=op["entity_id"],
                            op="delete", rev=existing.rev, hospital_id=hospital_id,
                            payload=incident_payload(existing))
        return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}

    # Validate the closed vocabularies; never store free text where a code belongs.
    incident_type = str(payload.get("incident_type") or "other")
    severity = str(payload.get("severity") or "moderate")
    patient_harm = str(payload.get("patient_harm") or "none")
    if incident_type not in INCIDENT_TYPES or severity not in INCIDENT_SEVERITIES or patient_harm not in INCIDENT_HARMS:
        return _reject(op_id, "validation_failed", "قيم الحادث غير صالحة.")

    title = str(payload.get("title") or "").strip()
    if len(title) < 3:
        return _reject(op_id, "validation_failed", "عنوان الحادث مطلوب.")

    department_id = payload.get("department_id")
    department_uuid = None
    if department_id:
        try:
            department_uuid = uuid.UUID(str(department_id))
        except (ValueError, TypeError):
            return _reject(op_id, "validation_failed", "القسم غير صالح.")
        dept = db.get(Department, department_uuid)
        if dept is None or dept.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "القسم لا يتبع هذا المستشفى.")

    if existing is None:
        if op["base_rev"] not in (0,):
            return _reject(op_id, "not_found", "السجل غير موجود على الخادم.")
        incident = Incident(
            id=entity_uuid,
            hospital_id=hospital_id,
            department_id=department_uuid,
            code=_next_incident_code(db, hospital_id),
            title=title,
            description=payload.get("description"),
            incident_type=incident_type,
            severity=severity,
            patient_harm=patient_harm,
            occurred_at=payload.get("occurred_at"),
            is_anonymous=bool(payload.get("is_anonymous", False)),
            status="reported",  # a node never creates an already-reviewed case
            immediate_action=payload.get("immediate_action"),
            reported_by=None if payload.get("is_anonymous") else identity.user.id,
        )
        db.add(incident)
        db.flush()
        seq = record_change(db, entity_type="incident", entity_id=op["entity_id"],
                            op="upsert", rev=incident.rev, hospital_id=hospital_id,
                            payload=incident_payload(incident))
        return {"op_id": op_id, "status": "applied", "new_rev": incident.rev, "server_seq": seq}

    # existing, upsert
    if existing.hospital_id != hospital_id:
        return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
    if existing.status == "closed":
        return _reject(
            op_id, "already_approved",
            "الحادث مغلق ولا يُعدَّل من الجهاز؛ أعده إلى المراجعة من الخادم أولاً.",
        )
    if op["base_rev"] != existing.rev:
        return _conflict(
            db, op_id=op_id, entity_type="incident", entity_id=op["entity_id"],
            node_id=node_id, hospital_id=hospital_id, local_payload=payload,
            server_payload=incident_payload(existing), current_rev=existing.rev,
        )
    existing.title = title
    existing.description = payload.get("description")
    existing.incident_type = incident_type
    existing.severity = severity
    existing.patient_harm = patient_harm
    existing.occurred_at = payload.get("occurred_at")
    existing.immediate_action = payload.get("immediate_action")
    existing.department_id = department_uuid
    existing.rev += 1
    existing.updated_at = _now()
    seq = record_change(db, entity_type="incident", entity_id=op["entity_id"],
                        op="upsert", rev=existing.rev, hospital_id=hospital_id,
                        payload=incident_payload(existing))
    return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}


def _next_quality_code(db: Session, model: type, hospital_id: uuid.UUID, prefix: str) -> str:
    """A per-hospital human reference (RSK-2026-0004), never reused."""
    year = _now().year
    count = db.execute(
        select(func.count()).select_from(model).where(model.hospital_id == hospital_id)
    ).scalar_one()
    return f"{prefix}-{year}-{int(count) + 1:04d}"


def _parse_due_date(value) -> date | None:
    """Accept an ISO date/datetime string; anything else is no due date."""
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _apply_capa(db: Session, identity: Identity, node_id: str, op: dict, hospital_id: uuid.UUID) -> dict:
    """Create or update a CAPA action planned on an offline node.

    The node owns the plan (title, kind, priority, owner, due date, note). The
    server owns the code and the sign-off: a device may set ``open`` or
    ``in_progress`` only, so it can never mark its own work ``done`` or
    ``verified`` (who completed and verified stays authoritative).
    """
    op_id = op["op_id"]
    payload = op.get("payload") or {}
    try:
        entity_uuid = uuid.UUID(op["entity_id"])
    except (ValueError, TypeError):
        return _reject(op_id, "bad_id", "معرّف السجل غير صالح.")

    existing = db.get(CapaAction, entity_uuid)

    if op["op"] == "delete":
        if existing is None:
            return {"op_id": op_id, "status": "applied", "new_rev": 0}
        if existing.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
        if op["base_rev"] != existing.rev:
            return _conflict(
                db, op_id=op_id, entity_type="capa_action", entity_id=op["entity_id"],
                node_id=node_id, hospital_id=hospital_id, local_payload=payload,
                server_payload=capa_payload(existing), current_rev=existing.rev,
            )
        existing.deleted_at = _now()
        existing.rev += 1
        seq = record_change(db, entity_type="capa_action", entity_id=op["entity_id"],
                            op="delete", rev=existing.rev, hospital_id=hospital_id,
                            payload=capa_payload(existing))
        return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}

    kind = str(payload.get("kind") or "corrective")
    priority = str(payload.get("priority") or "medium")
    status_value = str(payload.get("status") or "open")
    if kind not in CAPA_KINDS or priority not in CAPA_PRIORITIES or status_value not in CAPA_NODE_STATUSES:
        return _reject(op_id, "validation_failed", "قيم الإجراء التصحيحي غير صالحة.")

    title = str(payload.get("title") or "").strip()
    if len(title) < 3:
        return _reject(op_id, "validation_failed", "عنوان الإجراء مطلوب.")

    department_uuid = None
    department_id = payload.get("department_id")
    if department_id:
        try:
            department_uuid = uuid.UUID(str(department_id))
        except (ValueError, TypeError):
            return _reject(op_id, "validation_failed", "القسم غير صالح.")
        dept = db.get(Department, department_uuid)
        if dept is None or dept.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "القسم لا يتبع هذا المستشفى.")

    incident_uuid = None
    incident_id = payload.get("incident_id")
    if incident_id:
        try:
            incident_uuid = uuid.UUID(str(incident_id))
        except (ValueError, TypeError):
            return _reject(op_id, "validation_failed", "الحادث المرتبط غير صالح.")
        incident = db.get(Incident, incident_uuid)
        if incident is None or incident.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "الحادث لا يتبع هذا المستشفى.")

    if existing is None:
        if op["base_rev"] not in (0,):
            return _reject(op_id, "not_found", "السجل غير موجود على الخادم.")
        row = CapaAction(
            id=entity_uuid,
            hospital_id=hospital_id,
            department_id=department_uuid,
            incident_id=incident_uuid,
            kind=kind,
            title=title,
            description_ar=payload.get("description_ar"),
            owner_name_ar=payload.get("owner_name_ar"),
            due_date=_parse_due_date(payload.get("due_date")),
            priority=priority,
            status=status_value,
        )
        db.add(row)
        db.flush()
        seq = record_change(db, entity_type="capa_action", entity_id=op["entity_id"],
                            op="upsert", rev=row.rev, hospital_id=hospital_id,
                            payload=capa_payload(row))
        return {"op_id": op_id, "status": "applied", "new_rev": row.rev, "server_seq": seq}

    if existing.hospital_id != hospital_id:
        return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
    if existing.status in ("done", "verified"):
        return _reject(
            op_id, "already_approved",
            "الإجراء مُنجَز أو مُتحقَّق منه ولا يُعدَّل من الجهاز؛ أعده إلى التنفيذ من الخادم أولاً.",
        )
    if op["base_rev"] != existing.rev:
        return _conflict(
            db, op_id=op_id, entity_type="capa_action", entity_id=op["entity_id"],
            node_id=node_id, hospital_id=hospital_id, local_payload=payload,
            server_payload=capa_payload(existing), current_rev=existing.rev,
        )
    existing.title = title
    existing.kind = kind
    existing.priority = priority
    existing.status = status_value
    existing.description_ar = payload.get("description_ar")
    existing.owner_name_ar = payload.get("owner_name_ar")
    existing.due_date = _parse_due_date(payload.get("due_date"))
    existing.department_id = department_uuid
    existing.rev += 1
    existing.updated_at = _now()
    seq = record_change(db, entity_type="capa_action", entity_id=op["entity_id"],
                        op="upsert", rev=existing.rev, hospital_id=hospital_id,
                        payload=capa_payload(existing))
    return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}


def _apply_risk(db: Session, identity: Identity, node_id: str, op: dict, hospital_id: uuid.UUID) -> dict:
    """Create or update a risk-register entry from an offline node.

    The node owns the assessment (title, category, likelihood, impact,
    mitigation, owner, review date). The score is a generated column the server
    computes from likelihood × impact; a device never sends it. Closing a risk is
    a server-side decision, so a device may set open/mitigated/accepted only.
    """
    op_id = op["op_id"]
    payload = op.get("payload") or {}
    try:
        entity_uuid = uuid.UUID(op["entity_id"])
    except (ValueError, TypeError):
        return _reject(op_id, "bad_id", "معرّف السجل غير صالح.")

    existing = db.get(Risk, entity_uuid)

    if op["op"] == "delete":
        if existing is None:
            return {"op_id": op_id, "status": "applied", "new_rev": 0}
        if existing.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
        if op["base_rev"] != existing.rev:
            return _conflict(
                db, op_id=op_id, entity_type="risk", entity_id=op["entity_id"],
                node_id=node_id, hospital_id=hospital_id, local_payload=payload,
                server_payload=risk_payload(existing), current_rev=existing.rev,
            )
        existing.deleted_at = _now()
        existing.rev += 1
        seq = record_change(db, entity_type="risk", entity_id=op["entity_id"],
                            op="delete", rev=existing.rev, hospital_id=hospital_id,
                            payload=risk_payload(existing))
        return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}

    category = str(payload.get("category") or "clinical")
    status_value = str(payload.get("status") or "open")
    if category not in RISK_CATEGORIES or status_value not in RISK_NODE_STATUSES:
        return _reject(op_id, "validation_failed", "قيم الخطر غير صالحة.")

    try:
        likelihood = int(payload.get("likelihood", 3))
        impact = int(payload.get("impact", 3))
    except (ValueError, TypeError):
        return _reject(op_id, "validation_failed", "تقدير الاحتمال والأثر غير صالح.")
    if not (1 <= likelihood <= 5 and 1 <= impact <= 5):
        return _reject(op_id, "validation_failed", "الاحتمال والأثر بين ١ و٥.")

    title = str(payload.get("title") or "").strip()
    if len(title) < 3:
        return _reject(op_id, "validation_failed", "عنوان الخطر مطلوب.")

    department_uuid = None
    department_id = payload.get("department_id")
    if department_id:
        try:
            department_uuid = uuid.UUID(str(department_id))
        except (ValueError, TypeError):
            return _reject(op_id, "validation_failed", "القسم غير صالح.")
        dept = db.get(Department, department_uuid)
        if dept is None or dept.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "القسم لا يتبع هذا المستشفى.")

    if existing is None:
        if op["base_rev"] not in (0,):
            return _reject(op_id, "not_found", "السجل غير موجود على الخادم.")
        row = Risk(
            id=entity_uuid,
            hospital_id=hospital_id,
            department_id=department_uuid,
            code=_next_quality_code(db, Risk, hospital_id, "RSK"),
            title=title,
            description_ar=payload.get("description_ar"),
            category=category,
            likelihood=likelihood,
            impact=impact,
            mitigation_ar=payload.get("mitigation_ar"),
            owner_name_ar=payload.get("owner_name_ar"),
            review_date=_parse_due_date(payload.get("review_date")),
            status=status_value,
        )
        db.add(row)
        db.flush()
        seq = record_change(db, entity_type="risk", entity_id=op["entity_id"],
                            op="upsert", rev=row.rev, hospital_id=hospital_id,
                            payload=risk_payload(row))
        return {"op_id": op_id, "status": "applied", "new_rev": row.rev, "server_seq": seq}

    if existing.hospital_id != hospital_id:
        return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
    if existing.status == "closed":
        return _reject(
            op_id, "already_approved",
            "الخطر مغلق ولا يُعدَّل من الجهاز؛ أعده إلى المتابعة من الخادم أولاً.",
        )
    if op["base_rev"] != existing.rev:
        return _conflict(
            db, op_id=op_id, entity_type="risk", entity_id=op["entity_id"],
            node_id=node_id, hospital_id=hospital_id, local_payload=payload,
            server_payload=risk_payload(existing), current_rev=existing.rev,
        )
    existing.title = title
    existing.category = category
    existing.likelihood = likelihood
    existing.impact = impact
    existing.status = status_value
    existing.description_ar = payload.get("description_ar")
    existing.mitigation_ar = payload.get("mitigation_ar")
    existing.owner_name_ar = payload.get("owner_name_ar")
    existing.review_date = _parse_due_date(payload.get("review_date"))
    existing.department_id = department_uuid
    existing.rev += 1
    existing.updated_at = _now()
    seq = record_change(db, entity_type="risk", entity_id=op["entity_id"],
                        op="upsert", rev=existing.rev, hospital_id=hospital_id,
                        payload=risk_payload(existing))
    return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}


def _apply_audit(db: Session, identity: Identity, node_id: str, op: dict, hospital_id: uuid.UUID) -> dict:
    """Create or update an internal audit opened on an offline node.

    The node owns the plan (title, standard, scope, auditor, planned date). The
    code and the score are server-owned, and completing/closing an audit is a
    server-side decision: a device may set ``planned`` or ``in_progress`` only.
    """
    op_id = op["op_id"]
    payload = op.get("payload") or {}
    try:
        entity_uuid = uuid.UUID(op["entity_id"])
    except (ValueError, TypeError):
        return _reject(op_id, "bad_id", "معرّف السجل غير صالح.")

    existing = db.get(QualityAudit, entity_uuid)

    if op["op"] == "delete":
        if existing is None:
            return {"op_id": op_id, "status": "applied", "new_rev": 0}
        if existing.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
        if op["base_rev"] != existing.rev:
            return _conflict(
                db, op_id=op_id, entity_type="audit", entity_id=op["entity_id"],
                node_id=node_id, hospital_id=hospital_id, local_payload=payload,
                server_payload=audit_payload(existing), current_rev=existing.rev,
            )
        existing.deleted_at = _now()
        existing.rev += 1
        seq = record_change(db, entity_type="audit", entity_id=op["entity_id"],
                            op="delete", rev=existing.rev, hospital_id=hospital_id,
                            payload=audit_payload(existing))
        return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}

    status_value = str(payload.get("status") or "planned")
    if status_value not in AUDIT_NODE_STATUSES:
        return _reject(op_id, "validation_failed", "حالة التدقيق غير صالحة.")

    title = str(payload.get("title") or "").strip()
    if len(title) < 3:
        return _reject(op_id, "validation_failed", "عنوان التدقيق مطلوب.")

    department_uuid = None
    department_id = payload.get("department_id")
    if department_id:
        try:
            department_uuid = uuid.UUID(str(department_id))
        except (ValueError, TypeError):
            return _reject(op_id, "validation_failed", "القسم غير صالح.")
        dept = db.get(Department, department_uuid)
        if dept is None or dept.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "القسم لا يتبع هذا المستشفى.")

    if existing is None:
        if op["base_rev"] not in (0,):
            return _reject(op_id, "not_found", "السجل غير موجود على الخادم.")
        row = QualityAudit(
            id=entity_uuid,
            hospital_id=hospital_id,
            department_id=department_uuid,
            code=_next_quality_code(db, QualityAudit, hospital_id, "AUD"),
            title=title,
            standard_ar=payload.get("standard_ar"),
            scope_ar=payload.get("scope_ar"),
            auditor_name_ar=payload.get("auditor_name_ar"),
            audit_date=_parse_due_date(payload.get("audit_date")),
            status=status_value,
        )
        db.add(row)
        db.flush()
        seq = record_change(db, entity_type="audit", entity_id=op["entity_id"],
                            op="upsert", rev=row.rev, hospital_id=hospital_id,
                            payload=audit_payload(row))
        return {"op_id": op_id, "status": "applied", "new_rev": row.rev, "server_seq": seq}

    if existing.hospital_id != hospital_id:
        return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
    if existing.status in ("completed", "closed"):
        return _reject(
            op_id, "already_approved",
            "التدقيق مُكتمل أو مُغلق ولا يُعدَّل من الجهاز؛ أعده إلى التنفيذ من الخادم أولاً.",
        )
    if op["base_rev"] != existing.rev:
        return _conflict(
            db, op_id=op_id, entity_type="audit", entity_id=op["entity_id"],
            node_id=node_id, hospital_id=hospital_id, local_payload=payload,
            server_payload=audit_payload(existing), current_rev=existing.rev,
        )
    existing.title = title
    existing.standard_ar = payload.get("standard_ar")
    existing.scope_ar = payload.get("scope_ar")
    existing.auditor_name_ar = payload.get("auditor_name_ar")
    existing.audit_date = _parse_due_date(payload.get("audit_date"))
    existing.status = status_value
    existing.department_id = department_uuid
    existing.rev += 1
    existing.updated_at = _now()
    seq = record_change(db, entity_type="audit", entity_id=op["entity_id"],
                        op="upsert", rev=existing.rev, hospital_id=hospital_id,
                        payload=audit_payload(existing))
    return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}


def _apply_improvement_plan(
    db: Session, identity: Identity, node_id: str, op: dict, hospital_id: uuid.UUID
) -> dict:
    """Create or update an improvement plan drafted on an offline node.

    The node owns the draft (title, objective, baseline, target, owner, dates).
    The code is server-owned and completing/cancelling a plan is a server-side
    decision: a device may keep a plan ``draft`` or ``active`` only.
    """
    op_id = op["op_id"]
    payload = op.get("payload") or {}
    try:
        entity_uuid = uuid.UUID(op["entity_id"])
    except (ValueError, TypeError):
        return _reject(op_id, "bad_id", "معرّف السجل غير صالح.")

    existing = db.get(ImprovementPlan, entity_uuid)

    if op["op"] == "delete":
        if existing is None:
            return {"op_id": op_id, "status": "applied", "new_rev": 0}
        if existing.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
        if op["base_rev"] != existing.rev:
            return _conflict(
                db, op_id=op_id, entity_type="improvement_plan", entity_id=op["entity_id"],
                node_id=node_id, hospital_id=hospital_id, local_payload=payload,
                server_payload=improvement_plan_payload(existing), current_rev=existing.rev,
            )
        existing.deleted_at = _now()
        existing.rev += 1
        seq = record_change(db, entity_type="improvement_plan", entity_id=op["entity_id"],
                            op="delete", rev=existing.rev, hospital_id=hospital_id,
                            payload=improvement_plan_payload(existing))
        return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}

    status_value = str(payload.get("status") or "draft")
    if status_value not in PLAN_NODE_STATUSES:
        return _reject(op_id, "validation_failed", "حالة خطة التحسين غير صالحة.")

    title = str(payload.get("title") or "").strip()
    if len(title) < 3:
        return _reject(op_id, "validation_failed", "عنوان خطة التحسين مطلوب.")

    department_uuid = None
    department_id = payload.get("department_id")
    if department_id:
        try:
            department_uuid = uuid.UUID(str(department_id))
        except (ValueError, TypeError):
            return _reject(op_id, "validation_failed", "القسم غير صالح.")
        dept = db.get(Department, department_uuid)
        if dept is None or dept.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "القسم لا يتبع هذا المستشفى.")

    if existing is None:
        if op["base_rev"] not in (0,):
            return _reject(op_id, "not_found", "السجل غير موجود على الخادم.")
        row = ImprovementPlan(
            id=entity_uuid,
            hospital_id=hospital_id,
            department_id=department_uuid,
            code=_next_quality_code(db, ImprovementPlan, hospital_id, "IMP"),
            title=title,
            objective_ar=payload.get("objective_ar"),
            baseline_ar=payload.get("baseline_ar"),
            target_ar=payload.get("target_ar"),
            owner_name_ar=payload.get("owner_name_ar"),
            start_date=_parse_due_date(payload.get("start_date")),
            due_date=_parse_due_date(payload.get("due_date")),
            status=status_value,
        )
        db.add(row)
        db.flush()
        seq = record_change(db, entity_type="improvement_plan", entity_id=op["entity_id"],
                            op="upsert", rev=row.rev, hospital_id=hospital_id,
                            payload=improvement_plan_payload(row))
        return {"op_id": op_id, "status": "applied", "new_rev": row.rev, "server_seq": seq}

    if existing.hospital_id != hospital_id:
        return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
    if existing.status in ("completed", "cancelled"):
        return _reject(
            op_id, "already_approved",
            "خطة التحسين مُكتملة أو مُلغاة ولا تُعدَّل من الجهاز؛ أعِدها إلى التنفيذ من الخادم أولاً.",
        )
    if op["base_rev"] != existing.rev:
        return _conflict(
            db, op_id=op_id, entity_type="improvement_plan", entity_id=op["entity_id"],
            node_id=node_id, hospital_id=hospital_id, local_payload=payload,
            server_payload=improvement_plan_payload(existing), current_rev=existing.rev,
        )
    existing.title = title
    existing.objective_ar = payload.get("objective_ar")
    existing.baseline_ar = payload.get("baseline_ar")
    existing.target_ar = payload.get("target_ar")
    existing.owner_name_ar = payload.get("owner_name_ar")
    existing.start_date = _parse_due_date(payload.get("start_date"))
    existing.due_date = _parse_due_date(payload.get("due_date"))
    existing.status = status_value
    existing.department_id = department_uuid
    existing.rev += 1
    existing.updated_at = _now()
    seq = record_change(db, entity_type="improvement_plan", entity_id=op["entity_id"],
                        op="upsert", rev=existing.rev, hospital_id=hospital_id,
                        payload=improvement_plan_payload(existing))
    return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}


def _apply_improvement_action(
    db: Session, identity: Identity, node_id: str, op: dict, hospital_id: uuid.UUID
) -> dict:
    """Create or update a step under an improvement plan from an offline node.

    An action has no hospital of its own; it is scoped through its parent plan,
    which must belong to the pushing hospital. Marking a step done/cancelled is a
    server-side decision, so a device may set ``open`` or ``in_progress`` only.
    """
    op_id = op["op_id"]
    payload = op.get("payload") or {}
    try:
        entity_uuid = uuid.UUID(op["entity_id"])
    except (ValueError, TypeError):
        return _reject(op_id, "bad_id", "معرّف السجل غير صالح.")

    existing = db.get(ImprovementAction, entity_uuid)

    if op["op"] == "delete":
        if existing is None:
            return {"op_id": op_id, "status": "applied", "new_rev": 0}
        plan = db.get(ImprovementPlan, existing.plan_id)
        if plan is None or plan.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
        if op["base_rev"] != existing.rev:
            return _conflict(
                db, op_id=op_id, entity_type="improvement_action", entity_id=op["entity_id"],
                node_id=node_id, hospital_id=hospital_id, local_payload=payload,
                server_payload=improvement_action_payload(existing, hospital_id=plan.hospital_id),
                current_rev=existing.rev,
            )
        existing.deleted_at = _now()
        existing.rev += 1
        seq = record_change(db, entity_type="improvement_action", entity_id=op["entity_id"],
                            op="delete", rev=existing.rev, hospital_id=hospital_id,
                            payload=improvement_action_payload(existing, hospital_id=plan.hospital_id))
        return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}

    status_value = str(payload.get("status") or "open")
    if status_value not in ACTION_NODE_STATUSES:
        return _reject(op_id, "validation_failed", "حالة إجراء الخطة غير صالحة.")

    title = str(payload.get("title") or "").strip()
    if len(title) < 3:
        return _reject(op_id, "validation_failed", "عنوان إجراء الخطة مطلوب.")

    plan_uuid = None
    plan_id = payload.get("plan_id")
    if plan_id:
        try:
            plan_uuid = uuid.UUID(str(plan_id))
        except (ValueError, TypeError):
            return _reject(op_id, "validation_failed", "خطة التحسين غير صالحة.")

    if existing is None:
        if op["base_rev"] not in (0,):
            return _reject(op_id, "not_found", "السجل غير موجود على الخادم.")
        if plan_uuid is None:
            return _reject(op_id, "validation_failed", "إجراء الخطة يجب أن يرتبط بخطة تحسين.")
        plan = db.get(ImprovementPlan, plan_uuid)
        if plan is None or plan.hospital_id != hospital_id:
            return _reject(op_id, "forbidden", "خطة التحسين لا تتبع هذا المستشفى.")
        row = ImprovementAction(
            id=entity_uuid,
            plan_id=plan_uuid,
            title=title,
            owner_name_ar=payload.get("owner_name_ar"),
            due_date=_parse_due_date(payload.get("due_date")),
            status=status_value,
            note_ar=payload.get("note_ar"),
        )
        db.add(row)
        db.flush()
        seq = record_change(db, entity_type="improvement_action", entity_id=op["entity_id"],
                            op="upsert", rev=row.rev, hospital_id=hospital_id,
                            payload=improvement_action_payload(row, hospital_id=plan.hospital_id))
        return {"op_id": op_id, "status": "applied", "new_rev": row.rev, "server_seq": seq}

    plan = db.get(ImprovementPlan, existing.plan_id)
    if plan is None or plan.hospital_id != hospital_id:
        return _reject(op_id, "forbidden", "السجل لا يخصّ مستشفى هذا الجهاز.")
    if plan_uuid is not None and plan_uuid != existing.plan_id:
        return _reject(op_id, "validation_failed", "لا يمكن نقل إجراء الخطة إلى خطة أخرى.")
    if existing.status in ("done", "cancelled"):
        return _reject(
            op_id, "already_approved",
            "الإجراء مُنجَز أو مُلغى ولا يُعدَّل من الجهاز؛ أعده إلى التنفيذ من الخادم أولاً.",
        )
    if op["base_rev"] != existing.rev:
        return _conflict(
            db, op_id=op_id, entity_type="improvement_action", entity_id=op["entity_id"],
            node_id=node_id, hospital_id=hospital_id, local_payload=payload,
            server_payload=improvement_action_payload(existing, hospital_id=plan.hospital_id),
            current_rev=existing.rev,
        )
    existing.title = title
    existing.owner_name_ar = payload.get("owner_name_ar")
    existing.due_date = _parse_due_date(payload.get("due_date"))
    existing.status = status_value
    existing.note_ar = payload.get("note_ar")
    existing.rev += 1
    existing.updated_at = _now()
    seq = record_change(db, entity_type="improvement_action", entity_id=op["entity_id"],
                        op="upsert", rev=existing.rev, hospital_id=hospital_id,
                        payload=improvement_action_payload(existing, hospital_id=plan.hospital_id))
    return {"op_id": op_id, "status": "applied", "new_rev": existing.rev, "server_seq": seq}


def apply_operation(
    db: Session,
    *,
    identity: Identity,
    node_id: str,
    op: dict,
    hospital_id: uuid.UUID,
) -> dict:
    """Apply one operation with idempotency, then commit it on its own.

    Each operation is atomic: it either fully applies or is rejected; one
    failure never rolls back the rest of the batch (docs/14 §4.3).
    """
    # Idempotency: return the stored result if this op_id was already handled.
    seen = db.get(SyncIdempotency, op["op_id"])
    if seen is not None:
        return dict(seen.result)

    if op["entity_type"] not in PUSHABLE_ENTITIES:
        result = _reject(
            op["op_id"], "unsupported_entity",
            "هذا النوع من السجلات يُدار مركزيًا ولا يُرسَل من الجهاز.",
        )
    elif op["entity_type"] == "reporting_period":
        result = _apply_period(db, identity, node_id, op, hospital_id)
    elif op["entity_type"] == "incident":
        result = _apply_incident(db, identity, node_id, op, hospital_id)
    elif op["entity_type"] == "capa_action":
        result = _apply_capa(db, identity, node_id, op, hospital_id)
    elif op["entity_type"] == "risk":
        result = _apply_risk(db, identity, node_id, op, hospital_id)
    elif op["entity_type"] == "audit":
        result = _apply_audit(db, identity, node_id, op, hospital_id)
    elif op["entity_type"] == "improvement_plan":
        result = _apply_improvement_plan(db, identity, node_id, op, hospital_id)
    elif op["entity_type"] == "improvement_action":
        result = _apply_improvement_action(db, identity, node_id, op, hospital_id)
    else:
        result = _apply_value(db, identity, node_id, op, hospital_id)

    db.add(
        SyncIdempotency(
            op_id=op["op_id"],
            node_id=node_id,
            hospital_id=hospital_id,
            status=result["status"],
            result=result,
        )
    )
    db.commit()
    _apply_rls(db, identity)
    return result


def touch_node(
    db: Session,
    *,
    identity: Identity,
    node_id: str,
    hospital_id: uuid.UUID | None,
    last_seq: int | None = None,
) -> SyncNode:
    node = db.get(SyncNode, node_id)
    now = _now()
    if node is None:
        node = SyncNode(node_id=node_id, hospital_id=hospital_id, last_seq=last_seq or 0, last_seen_at=now)
        db.add(node)
    else:
        node.last_seen_at = now
        if hospital_id is not None:
            node.hospital_id = hospital_id
        if last_seq is not None:
            node.last_seq = last_seq
    db.commit()
    _apply_rls(db, identity)
    return node


# ---------------------------------------------------------------------------
# Pull / bootstrap / status
# ---------------------------------------------------------------------------
def pull_changes(db: Session, *, since: int, limit: int, hospital_id: uuid.UUID | None) -> dict:
    limit = max(1, min(limit, 1000))
    stmt = (
        select(ChangeLog)
        .where(ChangeLog.server_seq > since)
        .order_by(ChangeLog.server_seq)
        .limit(limit + 1)
    )
    if hospital_id is not None:
        # National rows (NULL) plus this hospital's rows. RLS enforces the same.
        stmt = stmt.where((ChangeLog.hospital_id.is_(None)) | (ChangeLog.hospital_id == hospital_id))
    rows = list(db.execute(stmt).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    changes = [
        {
            "server_seq": int(r.server_seq),
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "op": r.op,
            "rev": int(r.rev),
            "hospital_id": r.hospital_id,
            "payload": r.payload,
        }
        for r in rows
    ]
    to_seq = changes[-1]["server_seq"] if changes else since
    return {"from_seq": since, "to_seq": to_seq, "has_more": has_more, "changes": changes}


def bootstrap(db: Session, *, identity: Identity, node_id: str, hospital_id: uuid.UUID | None) -> dict:
    indicators = [
        {
            "id": str(i.id), "code": i.code, "name_ar": i.name_ar,
            "definition_ar": i.definition_ar, "purpose_ar": i.purpose_ar,
            "calculation_ar": i.calculation_ar, "computation": i.computation,
            "unit_ar": i.unit_ar, "data_source_ar": i.data_source_ar,
            "frequency": i.frequency, "responsible_party_ar": i.responsible_party_ar,
            "direction": i.direction, "target_value": _num(i.target_value),
            "acceptable_min": _num(i.acceptable_min), "acceptable_max": _num(i.acceptable_max),
            "multiplier": _num(i.multiplier), "numerator_label_ar": i.numerator_label_ar,
            "denominator_label_ar": i.denominator_label_ar, "is_active": i.is_active,
        }
        for i in db.execute(select(Indicator).where(Indicator.deleted_at.is_(None)).order_by(Indicator.code)).scalars()
    ]

    assignments: list[dict] = []
    periods: list[dict] = []
    departments: list[dict] = []
    incidents: list[dict] = []
    capa_actions: list[dict] = []
    risks: list[dict] = []
    audits: list[dict] = []
    improvement_plans: list[dict] = []
    improvement_actions: list[dict] = []
    if hospital_id is not None:
        assignments = [
            {
                "id": str(a.id), "indicator_id": str(a.indicator_id), "hospital_id": str(a.hospital_id),
                "department_id": _uid(a.department_id), "target_override": _num(a.target_override),
                "is_active": a.is_active,
            }
            for a in db.execute(
                select(IndicatorAssignment).where(
                    IndicatorAssignment.hospital_id == hospital_id,
                    IndicatorAssignment.deleted_at.is_(None),
                )
            ).scalars()
        ]
        periods = [
            period_payload(p)
            for p in db.execute(
                select(ReportingPeriod).where(
                    ReportingPeriod.hospital_id == hospital_id,
                    ReportingPeriod.deleted_at.is_(None),
                )
            ).scalars()
        ]
        departments = [
            {"id": str(d.id), "hospital_id": str(d.hospital_id), "name_ar": d.name_ar,
             "code": d.code, "is_active": d.is_active}
            for d in db.execute(
                select(Department).where(
                    Department.hospital_id == hospital_id,
                    Department.deleted_at.is_(None),
                )
            ).scalars()
        ]
        incidents = [
            incident_payload(i)
            for i in db.execute(
                select(Incident).where(
                    Incident.hospital_id == hospital_id,
                    Incident.deleted_at.is_(None),
                )
            ).scalars()
        ]
        capa_actions = [
            capa_payload(c)
            for c in db.execute(
                select(CapaAction).where(
                    CapaAction.hospital_id == hospital_id,
                    CapaAction.deleted_at.is_(None),
                )
            ).scalars()
        ]
        risks = [
            risk_payload(r)
            for r in db.execute(
                select(Risk).where(
                    Risk.hospital_id == hospital_id,
                    Risk.deleted_at.is_(None),
                )
            ).scalars()
        ]
        audits = [
            audit_payload(a)
            for a in db.execute(
                select(QualityAudit).where(
                    QualityAudit.hospital_id == hospital_id,
                    QualityAudit.deleted_at.is_(None),
                )
            ).scalars()
        ]
        improvement_plans = [
            improvement_plan_payload(p)
            for p in db.execute(
                select(ImprovementPlan).where(
                    ImprovementPlan.hospital_id == hospital_id,
                    ImprovementPlan.deleted_at.is_(None),
                )
            ).scalars()
        ]
        improvement_actions = [
            improvement_action_payload(a, hospital_id=hospital_id)
            for a in db.execute(
                select(ImprovementAction)
                .join(ImprovementPlan, ImprovementAction.plan_id == ImprovementPlan.id)
                .where(
                    ImprovementPlan.hospital_id == hospital_id,
                    ImprovementAction.deleted_at.is_(None),
                )
            ).scalars()
        ]

    return {
        "server_seq": current_seq(db),
        "hospital_id": hospital_id,
        "node_id": node_id,
        "indicators": indicators,
        "assignments": assignments,
        "periods": periods,
        "departments": departments,
        "incidents": incidents,
        "capa_actions": capa_actions,
        "risks": risks,
        "audits": audits,
        "improvement_plans": improvement_plans,
        "improvement_actions": improvement_actions,
    }


def status(db: Session, *, node_id: str | None, hospital_id: uuid.UUID | None) -> dict:
    seq = current_seq(db)
    node = db.get(SyncNode, node_id) if node_id else None
    last_seq = int(node.last_seq) if node is not None else 0
    pending = max(0, seq - last_seq)
    return {
        "node_id": node_id,
        "hospital_id": hospital_id,
        "last_seq": last_seq,
        "server_seq": seq,
        "pending_remote": pending,
        "last_seen_at": node.last_seen_at if node is not None else None,
    }


def resolve_hospital(identity: Identity, requested: uuid.UUID | None) -> uuid.UUID | None:
    """A node may only sync for a hospital it is allowed to see."""
    if identity.is_central:
        return requested or identity.hospital_id
    if identity.hospital_id is None:
        return None
    if requested is not None and requested != identity.hospital_id:
        return None
    return identity.hospital_id


def hospital_exists(db: Session, hospital_id: uuid.UUID) -> bool:
    hosp = db.get(Hospital, hospital_id)
    return hosp is not None and hosp.deleted_at is None
