"""ORM models for the v0.1 core."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> uuid.UUID:
    """UUIDv7 if available, else UUID4 (both are valid unique record ids)."""
    try:
        from uuid6 import uuid7  # type: ignore

        return uuid7()
    except Exception:
        return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("organizations.id"))
    level: Mapped[str] = mapped_column(Text, nullable=False)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Hospital(Base):
    __tablename__ = "hospitals"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("organizations.id"))
    governorate_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("organizations.id"))
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str | None] = mapped_column(Text)
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserAssignment(Base):
    __tablename__ = "user_assignments"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    role_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    before_json: Mapped[dict | None] = mapped_column(JSONB)
    after_json: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    node: Mapped[str | None] = mapped_column(Text)
    # Scope for row-level security (v0.11). NULL means a global event (a login,
    # a national-library edit) visible to the central administration only.
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"))


# ---- v0.4: national indicator library and reporting ----------------------


class Indicator(Base):
    __tablename__ = "indicators"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(Text, nullable=False)
    definition_ar: Mapped[str | None] = mapped_column(Text)
    purpose_ar: Mapped[str | None] = mapped_column(Text)
    calculation_ar: Mapped[str | None] = mapped_column(Text)
    computation: Mapped[str] = mapped_column(Text, default="entered", server_default="entered")
    unit_ar: Mapped[str | None] = mapped_column(Text)
    data_source_ar: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(Text, default="monthly", server_default="monthly")
    responsible_party_ar: Mapped[str | None] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text, default="higher_better", server_default="higher_better")
    target_value: Mapped[float | None] = mapped_column(Numeric)
    acceptable_min: Mapped[float | None] = mapped_column(Numeric)
    acceptable_max: Mapped[float | None] = mapped_column(Numeric)
    multiplier: Mapped[float] = mapped_column(Numeric, default=100, server_default="100")
    numerator_label_ar: Mapped[str | None] = mapped_column(Text)
    denominator_label_ar: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndicatorAssignment(Base):
    __tablename__ = "indicator_assignments"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    indicator_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("indicators.id"), nullable=False)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("departments.id"))
    target_override: Mapped[float | None] = mapped_column(Numeric)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportingPeriod(Base):
    __tablename__ = "reporting_periods"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    period_type: Mapped[str] = mapped_column(Text, default="monthly", server_default="monthly")
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int | None] = mapped_column(Integer)
    quarter: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default="draft", server_default="draft")
    note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    returned_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndicatorValue(Base):
    __tablename__ = "indicator_values"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    period_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("reporting_periods.id"), nullable=False)
    indicator_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("indicators.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("departments.id"))
    numerator: Mapped[float | None] = mapped_column(Numeric)
    denominator: Mapped[float | None] = mapped_column(Numeric)
    value: Mapped[float | None] = mapped_column(Numeric)
    value_type: Mapped[str] = mapped_column(Text, default="computed", server_default="computed")
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndicatorValueRevision(Base):
    __tablename__ = "indicator_value_revisions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    value_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("indicator_values.id"), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[float | None] = mapped_column(Numeric)
    new_value: Mapped[float | None] = mapped_column(Numeric)
    old_numerator: Mapped[float | None] = mapped_column(Numeric)
    new_numerator: Mapped[float | None] = mapped_column(Numeric)
    old_denominator: Mapped[float | None] = mapped_column(Numeric)
    new_denominator: Mapped[float | None] = mapped_column(Numeric)
    note: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChangeLog(Base):
    __tablename__ = "change_log"

    server_seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    op: Mapped[str] = mapped_column(Text, default="upsert", server_default="upsert")
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncIdempotency(Base):
    __tablename__ = "sync_idempotency"

    op_id: Mapped[str] = mapped_column(Text, primary_key=True)
    node_id: Mapped[str | None] = mapped_column(Text)
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConflictLog(Base):
    __tablename__ = "conflict_log"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    node_id: Mapped[str | None] = mapped_column(Text)
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"))
    local_payload: Mapped[dict | None] = mapped_column(JSONB)
    server_payload: Mapped[dict | None] = mapped_column(JSONB)
    resolution: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncNode(Base):
    __tablename__ = "sync_nodes"
    node_id: Mapped[str] = mapped_column(Text, primary_key=True)
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"))
    name: Mapped[str | None] = mapped_column(Text)
    last_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---- v0.7: quality and patient safety ------------------------------------


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("departments.id"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    incident_type: Mapped[str] = mapped_column(Text, default="other", server_default="other")
    severity: Mapped[str] = mapped_column(Text, default="moderate", server_default="moderate")
    patient_harm: Mapped[str] = mapped_column(Text, default="none", server_default="none")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reported_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(Text, default="reported", server_default="reported")
    immediate_action: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IncidentRca(Base):
    __tablename__ = "incident_rca"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    incident_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    method: Mapped[str] = mapped_column(Text, default="five_whys", server_default="five_whys")
    team_ar: Mapped[str | None] = mapped_column(Text)
    timeline_ar: Mapped[str | None] = mapped_column(Text)
    findings_ar: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    facilitator_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IncidentRcaCause(Base):
    __tablename__ = "incident_rca_causes"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    rca_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("incident_rca.id"), nullable=False)
    category: Mapped[str] = mapped_column(Text, default="other", server_default="other")
    description_ar: Mapped[str] = mapped_column(Text, nullable=False)
    is_root_cause: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CapaAction(Base):
    __tablename__ = "capa_actions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("departments.id"))
    incident_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("incidents.id"))
    rca_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("incident_rca.id"))
    audit_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("quality_audits.id"))
    kind: Mapped[str] = mapped_column(Text, default="corrective", server_default="corrective")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    owner_name_ar: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[datetime | None] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(Text, default="medium", server_default="medium")
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    completion_note_ar: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("departments.id"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, default="clinical", server_default="clinical")
    likelihood: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    impact: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    score: Mapped[int] = mapped_column(Integer, Computed("likelihood * impact", persisted=True))
    mitigation_ar: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    owner_name_ar: Mapped[str | None] = mapped_column(Text)
    review_date: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QualityAudit(Base):
    __tablename__ = "quality_audits"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("departments.id"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    standard_ar: Mapped[str | None] = mapped_column(Text)
    scope_ar: Mapped[str | None] = mapped_column(Text)
    auditor_name_ar: Mapped[str | None] = mapped_column(Text)
    audit_date: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, default="planned", server_default="planned")
    score: Mapped[float | None] = mapped_column(Numeric)
    findings_ar: Mapped[str | None] = mapped_column(Text)
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImprovementPlan(Base):
    __tablename__ = "improvement_plans"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("departments.id"))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    objective_ar: Mapped[str | None] = mapped_column(Text)
    baseline_ar: Mapped[str | None] = mapped_column(Text)
    target_ar: Mapped[str | None] = mapped_column(Text)
    indicator_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("indicators.id"))
    owner_name_ar: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[datetime | None] = mapped_column(Date)
    due_date: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, default="draft", server_default="draft")
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImprovementAction(Base):
    __tablename__ = "improvement_actions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    plan_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("improvement_plans.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    owner_name_ar: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    note_ar: Mapped[str | None] = mapped_column(Text)
    rev: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QualityDocument(Base):
    __tablename__ = "quality_documents"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(Text, default="policy", server_default="policy")
    version: Mapped[str] = mapped_column(Text, default="1.0", server_default="1.0")
    status: Mapped[str] = mapped_column(Text, default="draft", server_default="draft")
    summary_ar: Mapped[str | None] = mapped_column(Text)
    owner_name_ar: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[datetime | None] = mapped_column(Date)
    review_date: Mapped[datetime | None] = mapped_column(Date)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QualityMeeting(Base):
    __tablename__ = "quality_meetings"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    meeting_date: Mapped[datetime | None] = mapped_column(Date)
    location_ar: Mapped[str | None] = mapped_column(Text)
    chair_name_ar: Mapped[str | None] = mapped_column(Text)
    attendees_ar: Mapped[str | None] = mapped_column(Text)
    agenda_ar: Mapped[str | None] = mapped_column(Text)
    minutes_ar: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="scheduled", server_default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QualityMeetingDecision(Base):
    __tablename__ = "quality_meeting_decisions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    meeting_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("quality_meetings.id"), nullable=False)
    decision_ar: Mapped[str] = mapped_column(Text, nullable=False)
    owner_name_ar: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[datetime | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertAcknowledgement(Base):
    """A person's acknowledgement of one computed alert (v0.9).

    The alert list is recomputed from data on every read; this row only records
    that someone has seen a given alert (identified by its stable ``alert_key``)
    and what they noted. It never stores the alert body, so the list can never
    show a stale alert.
    """

    __tablename__ = "alert_acknowledgements"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    alert_key: Mapped[str] = mapped_column(Text, nullable=False)
    hospital_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"), nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    note_ar: Mapped[str | None] = mapped_column(Text)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertRule(Base):
    """A configurable threshold set for one alert kind (v0.10).

    ``hospital_id`` is NULL for the national default and set for a hospital
    override. ``params`` holds only the values that differ from the code
    defaults; the effective rule is the code default overlaid by the national
    row and then by the hospital row. Nothing about an alert body is stored here
    — only the numbers the engine reads when it computes alerts.
    """

    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("hospitals.id"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="'{}'::jsonb")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    note_ar: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
