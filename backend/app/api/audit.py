"""Audit-log endpoints (v0.11).

Read-only. The log is written everywhere else in the API; nothing here can add,
change or erase a record. Guarded by ``audit.view`` and always scoped by row
level security, so a hospital user only ever reads their own hospital's entries,
a governorate office its governorate's, and the central administration all.

Rows are returned newest-first with a readable Arabic summary, and the log can
be exported to CSV or Excel for review. Export honours the same filters and the
same scope as the on-screen list.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.base import get_db
from app.models.core import Hospital
from app.schemas import AuditFacetsOut, AuditLogPageOut
from app.services import audit as audit_service
from app.services import export as export_service
from app.services.identity import Identity

router = APIRouter(tags=["audit"])

EXPORT_MAX = 5000
EXPORT_NOTE = "سجل التدقيق — للقراءة فقط، ولا يمكن تعديله أو حذفه."


def _build_filters(
    identity: Identity,
    entity_type: str | None,
    action: str | None,
    actor_user_id: uuid.UUID | None,
    hospital_id: uuid.UUID | None,
    since: datetime | None,
    until: datetime | None,
    q: str | None,
    db: Session,
) -> audit_service.AuditFilters:
    """Turn request parameters into filters, clamping the hospital to scope."""
    scoped_hospital = hospital_id
    if not identity.is_central:
        if identity.hospital_id is not None:
            # A hospital user may only ever ask about their own hospital.
            if hospital_id is not None and hospital_id != identity.hospital_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": "forbidden", "message_ar": "لا تملك صلاحية على هذا المستشفى."},
                )
            scoped_hospital = identity.hospital_id
        elif hospital_id is not None:
            # Governorate or other scope: verify the hospital is in reach.
            hosp = db.get(Hospital, hospital_id)
            if hosp is None or hosp.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "not_found", "message_ar": "المستشفى غير موجود."},
                )
    return audit_service.AuditFilters(
        entity_type=entity_type or None,
        action=action or None,
        actor_user_id=actor_user_id,
        hospital_id=scoped_hospital,
        since=since,
        until=until,
        q=q or None,
    )


@router.get("/audit-log", response_model=AuditLogPageOut)
def list_audit_log(
    entity_type: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    actor_user_id: uuid.UUID | None = Query(default=None),
    hospital_id: uuid.UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    q: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=audit_service.DEFAULT_LIMIT, ge=1, le=audit_service.MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    identity: Identity = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> dict:
    filters = _build_filters(
        identity, entity_type, action, actor_user_id, hospital_id, since, until, q, db
    )
    total = audit_service.count_entries(db, filters)
    rows = audit_service.list_entries(db, filters, limit=limit, offset=offset)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": audit_service.serialize_many(db, rows),
    }


@router.get("/audit-log/facets", response_model=AuditFacetsOut)
def audit_facets(
    identity: Identity = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> dict:
    return audit_service.facets(db)


@router.get("/audit-log/export.csv")
def export_audit_csv(
    entity_type: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    actor_user_id: uuid.UUID | None = Query(default=None),
    hospital_id: uuid.UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    q: str | None = Query(default=None, max_length=128),
    identity: Identity = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> Response:
    filters = _build_filters(
        identity, entity_type, action, actor_user_id, hospital_id, since, until, q, db
    )
    rows = audit_service.dataset_for_export(db, filters, limit=EXPORT_MAX)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["الوقت", "المستخدم", "الإجراء", "الكيان", "المستشفى", "معرّف السجل"])
    writer.writerows(rows)
    # BOM so Excel opens the Arabic columns correctly.
    content = "\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )


@router.get("/audit-log/export.xlsx")
def export_audit_xlsx(
    entity_type: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    actor_user_id: uuid.UUID | None = Query(default=None),
    hospital_id: uuid.UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    q: str | None = Query(default=None, max_length=128),
    identity: Identity = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
) -> Response:
    filters = _build_filters(
        identity, entity_type, action, actor_user_id, hospital_id, since, until, q, db
    )
    rows = audit_service.dataset_for_export(db, filters, limit=EXPORT_MAX)
    content = export_service.build_excel(
        title="سجل التدقيق",
        subtitle=EXPORT_NOTE,
        columns=["الوقت", "المستخدم", "الإجراء", "الكيان", "المستشفى", "معرّف السجل"],
        rows=rows,
        sheet_name="سجل التدقيق",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="audit-log.xlsx"'},
    )
