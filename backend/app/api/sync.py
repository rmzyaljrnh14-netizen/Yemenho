"""Sync API (v0.6): push, pull, bootstrap, status.

Every endpoint is scoped to the caller's hospital (a node cannot sync another
hospital's data). The node id identifies the device so the ministry can see who
last synced and how far behind each device is.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_identity, require_permission
from app.db.base import get_db
from app.schemas import (
    SyncBootstrapResponse,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
    SyncStatusResponse,
)
from app.services import sync as sync_service
from app.services.identity import Identity, write_audit

router = APIRouter(tags=["sync"])


def _resolve(db: Session, identity: Identity, requested: uuid.UUID | None) -> uuid.UUID:
    hospital_id = sync_service.resolve_hospital(identity, requested)
    if hospital_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message_ar": "لا يمكنك المزامنة لمستشفى غير مصرّح به."},
        )
    if not sync_service.hospital_exists(db, hospital_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message_ar": "المستشفى غير موجود."},
        )
    return hospital_id


@router.post("/sync/push", response_model=SyncPushResponse)
def push(
    payload: SyncPushRequest,
    identity: Identity = Depends(require_permission("indicator.enter")),
    db: Session = Depends(get_db),
) -> dict:
    hospital_id = _resolve(db, identity, payload.hospital_id)
    results = [
        sync_service.apply_operation(
            db, identity=identity, node_id=payload.node_id, op=op.model_dump(), hospital_id=hospital_id
        )
        for op in payload.operations
    ]
    seq = sync_service.current_seq(db)
    sync_service.touch_node(db, identity=identity, node_id=payload.node_id, hospital_id=hospital_id, last_seq=seq)
    write_audit(
        db, entity_type="sync", entity_id=payload.batch_id, action="push",
        actor_user_id=identity.user.id, node=payload.node_id,
        after={"operations": len(results), "server_seq": seq},
        hospital_id=hospital_id,
    )
    db.commit()
    return {"batch_id": payload.batch_id, "server_seq": seq, "results": results}


@router.get("/sync/pull", response_model=SyncPullResponse)
def pull(
    since: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
    node_id: str | None = Query(default=None),
    identity: Identity = Depends(require_permission("indicator.enter")),
    db: Session = Depends(get_db),
) -> dict:
    hospital_id = sync_service.resolve_hospital(identity, None)
    result = sync_service.pull_changes(db, since=since, limit=limit, hospital_id=hospital_id)
    if node_id:
        sync_service.touch_node(db, identity=identity, node_id=node_id, hospital_id=hospital_id, last_seq=result["to_seq"])
    return result


@router.post("/sync/bootstrap", response_model=SyncBootstrapResponse)
def bootstrap(
    node_id: str = Query(min_length=1, max_length=128),
    hospital_id: uuid.UUID | None = Query(default=None),
    identity: Identity = Depends(require_permission("indicator.enter")),
    db: Session = Depends(get_db),
) -> dict:
    resolved = _resolve(db, identity, hospital_id) if hospital_id else sync_service.resolve_hospital(identity, None)
    result = sync_service.bootstrap(db, identity=identity, node_id=node_id, hospital_id=resolved)
    sync_service.touch_node(db, identity=identity, node_id=node_id, hospital_id=resolved, last_seq=result["server_seq"])
    return result


@router.get("/sync/status", response_model=SyncStatusResponse)
def get_status(
    node_id: str | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> dict:
    hospital_id = sync_service.resolve_hospital(identity, None)
    return sync_service.status(db, node_id=node_id, hospital_id=hospital_id)
