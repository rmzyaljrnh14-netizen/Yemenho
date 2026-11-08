"""Audit-log reading (v0.11).

The log itself has been written since v0.1 by ``write_audit``; this module only
*reads* it, and it never edits or deletes a record. Every query runs inside the
caller's row-level security scope, so a hospital user sees their own hospital's
entries, a governorate office its governorate's, and central sees everything.

Entries are returned newest-first with a plain-Arabic ``summary_ar`` line built
from the action and entity, so the screen reads like a sentence rather than a
table of codes. The Arabic labels live here (data, not UI text) so the desktop
app, the web portal and any future client all render the same words.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.core import AuditLog, Hospital, User

# Arabic labels. Keys are the exact codes written by write_audit callers.
ENTITY_LABELS: dict[str, str] = {
    "auth": "الدخول والجلسات",
    "user": "المستخدمون",
    "user_assignment": "إسناد الأدوار",
    "organization": "المؤسسات",
    "hospital": "المستشفيات",
    "department": "الأقسام",
    "indicator": "المؤشرات",
    "indicator_assignment": "إسناد المؤشرات",
    "indicator_value": "قيم المؤشرات",
    "reporting_period": "الفترات والتقارير",
    "sync": "المزامنة",
    "incident": "الحوادث",
    "incident_rca": "تحليل الأسباب الجذرية",
    "incident_rca_cause": "أسباب الحادث",
    "capa_action": "الإجراءات التصحيحية والوقائية",
    "risk": "سجل المخاطر",
    "quality_audit": "التدقيق الداخلي",
    "improvement_plan": "خطط التحسين",
    "improvement_action": "إجراءات التحسين",
    "quality_document": "وثائق الجودة",
    "quality_meeting": "اجتماعات الجودة",
    "quality_meeting_decision": "قرارات اجتماعات الجودة",
}

ACTION_LABELS: dict[str, str] = {
    "create": "إنشاء",
    "update": "تعديل",
    "delete": "حذف",
    "submit": "إرسال للمراجعة",
    "review": "مراجعة",
    "approve": "اعتماد",
    "return": "إعادة للتعديل",
    "login_success": "دخول ناجح",
    "login_failed": "محاولة دخول فاشلة",
    "logout": "خروج",
    "push": "دفع دفعة مزامنة",
}

# Readable phrasing per action; the entity label is appended after it.
ACTION_PHRASES: dict[str, str] = {
    "create": "أنشأ سجلاً في",
    "update": "عدّل سجلاً في",
    "delete": "حذف سجلاً في",
    "submit": "أرسل للمراجعة في",
    "review": "راجع في",
    "approve": "اعتمد في",
    "return": "أعاد للتعديل في",
    "login_success": "سجّل دخوله إلى",
    "login_failed": "فشلت محاولة دخوله إلى",
    "logout": "سجّل خروجه من",
    "push": "دفع تغييرات المزامنة في",
}

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def entity_label(code: str) -> str:
    return ENTITY_LABELS.get(code, code)


def action_label(code: str) -> str:
    return ACTION_LABELS.get(code, code)


@dataclass
class AuditFilters:
    entity_type: str | None = None
    action: str | None = None
    actor_user_id: uuid.UUID | None = None
    hospital_id: uuid.UUID | None = None
    since: datetime | None = None
    until: datetime | None = None
    q: str | None = None


def _base_query(filters: AuditFilters) -> Select:
    stmt = select(AuditLog)
    if filters.entity_type:
        stmt = stmt.where(AuditLog.entity_type == filters.entity_type)
    if filters.action:
        stmt = stmt.where(AuditLog.action == filters.action)
    if filters.actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == filters.actor_user_id)
    if filters.hospital_id:
        stmt = stmt.where(AuditLog.hospital_id == filters.hospital_id)
    if filters.since is not None:
        stmt = stmt.where(AuditLog.at >= filters.since)
    if filters.until is not None:
        stmt = stmt.where(AuditLog.at <= filters.until)
    if filters.q:
        needle = f"%{filters.q.strip()}%"
        stmt = stmt.where(
            or_(
                AuditLog.entity_id.ilike(needle),
                AuditLog.entity_type.ilike(needle),
                AuditLog.action.ilike(needle),
            )
        )
    return stmt


def count_entries(db: Session, filters: AuditFilters) -> int:
    sub = _base_query(filters).with_only_columns(AuditLog.id).subquery()
    return int(db.execute(select(func.count()).select_from(sub)).scalar_one())


def list_entries(
    db: Session, filters: AuditFilters, *, limit: int = DEFAULT_LIMIT, offset: int = 0
) -> list[AuditLog]:
    stmt = (
        _base_query(filters)
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())


def _lookup_names(
    db: Session, rows: list[AuditLog]
) -> tuple[dict[uuid.UUID, User], dict[uuid.UUID, str]]:
    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id is not None}
    hospital_ids = {r.hospital_id for r in rows if r.hospital_id is not None}

    actors: dict[uuid.UUID, User] = {}
    if actor_ids:
        for user in db.execute(select(User).where(User.id.in_(actor_ids))).scalars().all():
            actors[user.id] = user

    hospitals: dict[uuid.UUID, str] = {}
    if hospital_ids:
        for hid, name in db.execute(
            select(Hospital.id, Hospital.name_ar).where(Hospital.id.in_(hospital_ids))
        ).all():
            hospitals[hid] = name
    return actors, hospitals


def serialize(row: AuditLog, actors: dict[uuid.UUID, User], hospitals: dict[uuid.UUID, str]) -> dict:
    actor = actors.get(row.actor_user_id) if row.actor_user_id else None
    actor_name = actor.display_name if actor else None
    actor_username = actor.username if actor else None

    elabel = entity_label(row.entity_type)
    alabel = action_label(row.action)
    phrase = ACTION_PHRASES.get(row.action, "نفّذ إجراءً على")
    subject = actor_name or "النظام"
    summary = f"{subject} {phrase} {elabel}"

    return {
        "id": str(row.id),
        "at": row.at,
        "entity_type": row.entity_type,
        "entity_label_ar": elabel,
        "entity_id": row.entity_id,
        "action": row.action,
        "action_label_ar": alabel,
        "summary_ar": summary,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "actor_name": actor_name,
        "actor_username": actor_username,
        "hospital_id": str(row.hospital_id) if row.hospital_id else None,
        "hospital_name_ar": hospitals.get(row.hospital_id) if row.hospital_id else None,
        "node": row.node,
        "before": row.before_json,
        "after": row.after_json,
    }


def serialize_many(db: Session, rows: list[AuditLog]) -> list[dict]:
    actors, hospitals = _lookup_names(db, rows)
    return [serialize(r, actors, hospitals) for r in rows]


def facets(db: Session) -> dict:
    """Distinct entity types and actions present in the caller's scope.

    The screen uses these to build its filter menus, so it never offers a filter
    that would return nothing.
    """
    entity_rows = db.execute(
        select(AuditLog.entity_type, func.count())
        .group_by(AuditLog.entity_type)
        .order_by(func.count().desc())
    ).all()
    action_rows = db.execute(
        select(AuditLog.action, func.count())
        .group_by(AuditLog.action)
        .order_by(func.count().desc())
    ).all()
    actor_rows = db.execute(
        select(AuditLog.actor_user_id, func.count())
        .where(AuditLog.actor_user_id.is_not(None))
        .group_by(AuditLog.actor_user_id)
        .order_by(func.count().desc())
        .limit(50)
    ).all()

    actor_ids = [r[0] for r in actor_rows]
    actors: dict[uuid.UUID, User] = {}
    if actor_ids:
        for user in db.execute(select(User).where(User.id.in_(actor_ids))).scalars().all():
            actors[user.id] = user

    return {
        "entity_types": [
            {"code": code, "label_ar": entity_label(code), "count": int(n)}
            for code, n in entity_rows
        ],
        "actions": [
            {"code": code, "label_ar": action_label(code), "count": int(n)}
            for code, n in action_rows
        ],
        "actors": [
            {
                "user_id": str(uid),
                "name": actors[uid].display_name if uid in actors else str(uid),
                "username": actors[uid].username if uid in actors else None,
                "count": int(n),
            }
            for uid, n in actor_rows
        ],
    }


def dataset_for_export(db: Session, filters: AuditFilters, *, limit: int = 5000) -> list[list[object]]:
    """Rows shaped for the Excel/PDF builders, oldest-first for a readable log."""
    stmt = (
        _base_query(filters)
        .order_by(AuditLog.at.asc(), AuditLog.id.asc())
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars().all())
    actors, hospitals = _lookup_names(db, rows)
    data: list[list[object]] = []
    for r in rows:
        item = serialize(r, actors, hospitals)
        data.append(
            [
                item["at"].strftime("%Y-%m-%d %H:%M") if item["at"] else "",
                item["actor_name"] or "—",
                item["action_label_ar"],
                item["entity_label_ar"],
                item["hospital_name_ar"] or "—",
                item["entity_id"],
            ]
        )
    return data
