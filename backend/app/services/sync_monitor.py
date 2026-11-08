"""National sync monitor (v0.12).

Reads the sync picture the ministry needs: which hospital devices are reporting,
how far behind they are, and which edits collided. Conflicts are *already* logged
by the sync engine (``conflict_log``); this module surfaces them so a person can
review and dismiss them, and never silently loses the losing side.

Everything runs inside the caller's row-level security scope: a hospital user
sees their own device and their own conflicts, a governorate office sees its
hospitals, and the central administration sees every device. Nothing here edits
the underlying business data — resolving a conflict only records that a person
reviewed it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.core import ConflictLog, Hospital, SyncNode, User
from app.services.audit import entity_label
from app.services.identity import Identity, write_audit

# A device that has not been seen for this many days is reported as stale.
STALE_DAYS = 7
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# Resolution codes a person may set on a conflict.
RESOLUTIONS = {"reviewed", "dismissed"}
RESOLUTION_LABEL_AR = {
    "auto_server": "اعتُمدت نسخة الخادم تلقائياً",
    "reviewed": "راجعه مسؤول واعتمده",
    "dismissed": "استُبعد بلا إجراء",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_days(at: datetime | None) -> int | None:
    if at is None:
        return None
    delta = _now() - at
    return max(0, int(delta.total_seconds() // 86400))


def _hospital_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return {
        hid: name
        for hid, name in db.execute(
            select(Hospital.id, Hospital.name_ar).where(Hospital.id.in_(ids))
        ).all()
    }


# ---------------------------------------------------------------------------
# Devices (sync nodes)
# ---------------------------------------------------------------------------
def list_nodes(db: Session, *, only_stale: bool = False) -> list[dict]:
    rows = list(
        db.execute(select(SyncNode).order_by(SyncNode.last_seen_at.desc().nullslast())).scalars()
    )
    names = _hospital_names(db, {r.hospital_id for r in rows if r.hospital_id is not None})
    out: list[dict] = []
    for r in rows:
        age = _age_days(r.last_seen_at)
        stale = r.last_seen_at is None or (age is not None and age >= STALE_DAYS)
        if only_stale and not stale:
            continue
        out.append(
            {
                "node_id": r.node_id,
                "hospital_id": str(r.hospital_id) if r.hospital_id else None,
                "hospital_name_ar": names.get(r.hospital_id) if r.hospital_id else None,
                "name": r.name,
                "last_seq": int(r.last_seq),
                "last_seen_at": r.last_seen_at,
                "days_since_seen": age,
                "status": "stale" if stale else "ok",
                "status_label_ar": "متأخر" if stale else "منتظم",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------
def _serialize_conflict(
    c: ConflictLog, hospitals: dict[uuid.UUID, str], actors: dict[uuid.UUID, User]
) -> dict:
    actor = actors.get(c.resolved_by) if c.resolved_by else None
    return {
        "id": str(c.id),
        "entity_type": c.entity_type,
        "entity_label_ar": entity_label(c.entity_type),
        "entity_id": c.entity_id,
        "node_id": c.node_id,
        "hospital_id": str(c.hospital_id) if c.hospital_id else None,
        "hospital_name_ar": hospitals.get(c.hospital_id) if c.hospital_id else None,
        "resolution": c.resolution,
        "resolution_label_ar": RESOLUTION_LABEL_AR.get(c.resolution, c.resolution),
        "resolved_by": str(c.resolved_by) if c.resolved_by else None,
        "resolved_by_name": actor.display_name if actor else None,
        "resolved_at": c.resolved_at,
        "created_at": c.created_at,
        "local_payload": c.local_payload,
        "server_payload": c.server_payload,
    }


def _load_names(
    db: Session, rows: list[ConflictLog]
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, User]]:
    hospitals = _hospital_names(db, {r.hospital_id for r in rows if r.hospital_id is not None})
    actor_ids = {r.resolved_by for r in rows if r.resolved_by is not None}
    actors: dict[uuid.UUID, User] = {}
    if actor_ids:
        for user in db.execute(select(User).where(User.id.in_(actor_ids))).scalars().all():
            actors[user.id] = user
    return hospitals, actors


def count_conflicts(db: Session, *, include_resolved: bool = False) -> int:
    stmt = select(func.count()).select_from(ConflictLog)
    if not include_resolved:
        stmt = stmt.where(ConflictLog.resolution == "auto_server")
    return int(db.execute(stmt).scalar_one())


def list_conflicts(
    db: Session,
    *,
    include_resolved: bool = False,
    hospital_id: uuid.UUID | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict]:
    stmt = select(ConflictLog)
    if not include_resolved:
        stmt = stmt.where(ConflictLog.resolution == "auto_server")
    if hospital_id is not None:
        stmt = stmt.where(ConflictLog.hospital_id == hospital_id)
    stmt = stmt.order_by(ConflictLog.created_at.desc(), ConflictLog.id.desc()).limit(limit).offset(offset)
    rows = list(db.execute(stmt).scalars().all())
    hospitals, actors = _load_names(db, rows)
    return [_serialize_conflict(r, hospitals, actors) for r in rows]


def get_conflict(db: Session, conflict_id: uuid.UUID) -> ConflictLog | None:
    return db.get(ConflictLog, conflict_id)


def resolve_conflict(
    db: Session,
    *,
    identity: Identity,
    conflict: ConflictLog,
    resolution: str,
    note_ar: str | None = None,
) -> None:
    """Record that a person reviewed a conflict. Never touches the data itself."""
    conflict.resolution = resolution
    conflict.resolved_by = identity.user.id
    conflict.resolved_at = _now()
    write_audit(
        db,
        entity_type="sync",
        entity_id=str(conflict.id),
        action="resolve_conflict",
        actor_user_id=identity.user.id,
        node=conflict.node_id,
        after={
            "resolution": resolution,
            "note_ar": (note_ar or "").strip() or None,
            "entity_type": conflict.entity_type,
            "entity_id": conflict.entity_id,
        },
        hospital_id=conflict.hospital_id,
    )
    db.commit()


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
def overview(db: Session) -> dict:
    nodes = list_nodes(db)
    stale = [n for n in nodes if n["status"] == "stale"]
    open_conflicts = count_conflicts(db, include_resolved=False)
    resolved_conflicts = count_conflicts(db, include_resolved=True) - open_conflicts
    return {
        "devices_total": len(nodes),
        "devices_ok": len(nodes) - len(stale),
        "devices_stale": len(stale),
        "open_conflicts": open_conflicts,
        "resolved_conflicts": max(0, resolved_conflicts),
        "stale_days": STALE_DAYS,
    }
