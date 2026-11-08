"""National sync monitor (v0.12).

Read-only views of device health and conflicts, plus one action: marking a
conflict as reviewed or dismissed. Everything is scoped by row-level security,
so a hospital user sees their own device and conflicts and central sees all.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.base import get_db
from app.schemas import (
    SyncConflictPageOut,
    SyncConflictResolve,
    SyncMonitorOverviewOut,
    SyncDeviceOut,
)
from app.services import sync_monitor
from app.services.identity import Identity

router = APIRouter(tags=["sync-monitor"])


@router.get("/sync-monitor/overview", response_model=SyncMonitorOverviewOut)
def overview(
    identity: Identity = Depends(require_permission("sync.view")),
    db: Session = Depends(get_db),
) -> dict:
    return sync_monitor.overview(db)


@router.get("/sync-monitor/devices", response_model=list[SyncDeviceOut])
def devices(
    only_stale: bool = Query(default=False),
    identity: Identity = Depends(require_permission("sync.view")),
    db: Session = Depends(get_db),
) -> list[dict]:
    return sync_monitor.list_nodes(db, only_stale=only_stale)


@router.get("/sync-monitor/conflicts", response_model=SyncConflictPageOut)
def conflicts(
    include_resolved: bool = Query(default=False),
    hospital_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=sync_monitor.DEFAULT_LIMIT, ge=1, le=sync_monitor.MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    identity: Identity = Depends(require_permission("sync.view")),
    db: Session = Depends(get_db),
) -> dict:
    if not identity.is_central and identity.hospital_id is not None:
        if hospital_id is not None and hospital_id != identity.hospital_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message_ar": "لا تملك صلاحية على هذا المستشفى."},
            )
        hospital_id = identity.hospital_id
    total = sync_monitor.count_conflicts(db, include_resolved=include_resolved)
    entries = sync_monitor.list_conflicts(
        db, include_resolved=include_resolved, hospital_id=hospital_id, limit=limit, offset=offset
    )
    return {"total": total, "limit": limit, "offset": offset, "entries": entries}


@router.post("/sync-monitor/conflicts/{conflict_id}/resolve", response_model=dict)
def resolve(
    conflict_id: uuid.UUID,
    payload: SyncConflictResolve,
    identity: Identity = Depends(require_permission("sync.manage")),
    db: Session = Depends(get_db),
) -> dict:
    conflict = sync_monitor.get_conflict(db, conflict_id)
    if conflict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "التعارض غير موجود."},
        )
    sync_monitor.resolve_conflict(
        db,
        identity=identity,
        conflict=conflict,
        resolution=payload.resolution,
        note_ar=payload.note_ar,
    )
    return {"id": str(conflict.id), "resolution": conflict.resolution}
