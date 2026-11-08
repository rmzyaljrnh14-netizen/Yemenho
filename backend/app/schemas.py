"""Pydantic request/response schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Auth ----
class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=256)
    client_node: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ScopeOrg(BaseModel):
    level: str
    hospital_id: uuid.UUID | None = None
    governorate_id: uuid.UUID | None = None


class MeResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    is_active: bool
    roles: list[str]
    scopes: list[str]
    scope_org: ScopeOrg


# ---- Organizations ----
class OrganizationCreate(BaseModel):
    name_ar: str = Field(min_length=2, max_length=200)
    level: str = Field(pattern="^(central|governorate|district|hospital)$")
    parent_id: uuid.UUID | None = None
    code: str | None = None


class OrganizationOut(ORMModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    level: str
    name_ar: str
    code: str | None


# ---- Hospitals ----
class HospitalCreate(BaseModel):
    name_ar: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=64)
    governorate_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None


class HospitalOut(ORMModel):
    id: uuid.UUID
    name_ar: str
    code: str
    governorate_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    is_active: bool


# ---- Departments ----
class DepartmentCreate(BaseModel):
    name_ar: str = Field(min_length=2, max_length=200)
    hospital_id: uuid.UUID
    code: str | None = None
    manager_user_id: uuid.UUID | None = None


class DepartmentOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    name_ar: str
    code: str | None
    is_active: bool


# ---- Users ----
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=256)
    email: EmailStr | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    username: str
    display_name: str
    email: str | None
    is_active: bool
    created_at: datetime


class AssignmentCreate(BaseModel):
    user_id: uuid.UUID
    role_code: str = Field(min_length=2, max_length=64)
    scope_type: str = Field(pattern="^(central|governorate|hospital|department)$")
    scope_id: uuid.UUID | None = None


class AssignmentOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID | None


# ---- Audit ----
class AuditLogOut(ORMModel):
    id: uuid.UUID
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: uuid.UUID | None
    at: datetime
    node: str | None


# ---- Indicators (library) ----
COMPUTATIONS = "^(ratio|rate|percent|count|average|sum|entered)$"
DIRECTIONS = "^(higher_better|lower_better|target_range)$"
FREQUENCIES = "^(monthly|quarterly|semi_annual|annual)$"


class IndicatorCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name_ar: str = Field(min_length=2, max_length=300)
    definition_ar: str | None = None
    purpose_ar: str | None = None
    calculation_ar: str | None = None
    computation: str = Field(default="entered", pattern=COMPUTATIONS)
    unit_ar: str | None = None
    data_source_ar: str | None = None
    frequency: str = Field(default="monthly", pattern=FREQUENCIES)
    responsible_party_ar: str | None = None
    direction: str = Field(default="higher_better", pattern=DIRECTIONS)
    target_value: float | None = None
    acceptable_min: float | None = None
    acceptable_max: float | None = None
    multiplier: float = 100
    numerator_label_ar: str | None = None
    denominator_label_ar: str | None = None
    is_active: bool = True


class IndicatorUpdate(BaseModel):
    name_ar: str | None = Field(default=None, min_length=2, max_length=300)
    definition_ar: str | None = None
    purpose_ar: str | None = None
    calculation_ar: str | None = None
    computation: str | None = Field(default=None, pattern=COMPUTATIONS)
    unit_ar: str | None = None
    data_source_ar: str | None = None
    frequency: str | None = Field(default=None, pattern=FREQUENCIES)
    responsible_party_ar: str | None = None
    direction: str | None = Field(default=None, pattern=DIRECTIONS)
    target_value: float | None = None
    acceptable_min: float | None = None
    acceptable_max: float | None = None
    multiplier: float | None = None
    numerator_label_ar: str | None = None
    denominator_label_ar: str | None = None
    is_active: bool | None = None


class IndicatorOut(ORMModel):
    id: uuid.UUID
    code: str
    name_ar: str
    definition_ar: str | None
    purpose_ar: str | None
    calculation_ar: str | None
    computation: str
    unit_ar: str | None
    data_source_ar: str | None
    frequency: str
    responsible_party_ar: str | None
    direction: str
    target_value: float | None
    acceptable_min: float | None
    acceptable_max: float | None
    multiplier: float
    numerator_label_ar: str | None
    denominator_label_ar: str | None
    is_active: bool


# ---- Indicator assignments ----
class AssignmentUpsert(BaseModel):
    indicator_id: uuid.UUID
    hospital_id: uuid.UUID
    department_id: uuid.UUID | None = None
    target_override: float | None = None


class IndicatorAssignmentOut(ORMModel):
    id: uuid.UUID
    indicator_id: uuid.UUID
    hospital_id: uuid.UUID
    department_id: uuid.UUID | None
    target_override: float | None
    is_active: bool


class AssignedIndicatorOut(BaseModel):
    """An indicator together with where it applies and its effective target."""

    assignment_id: uuid.UUID
    indicator: IndicatorOut
    department_id: uuid.UUID | None
    target_override: float | None


# ---- Reporting periods and values ----
class PeriodCreate(BaseModel):
    hospital_id: uuid.UUID
    period_type: str = Field(default="monthly", pattern="^(monthly|quarterly|annual)$")
    year: int = Field(ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    quarter: int | None = Field(default=None, ge=1, le=4)


class PeriodOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    period_type: str
    year: int
    month: int | None
    quarter: int | None
    status: str
    note: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    approved_at: datetime | None
    returned_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ValueUpsert(BaseModel):
    indicator_id: uuid.UUID
    department_id: uuid.UUID | None = None
    numerator: float | None = None
    denominator: float | None = None
    entered_value: float | None = None
    note: str | None = None


class ValueOut(ORMModel):
    id: uuid.UUID
    period_id: uuid.UUID
    indicator_id: uuid.UUID
    department_id: uuid.UUID | None
    numerator: float | None
    denominator: float | None
    value: float | None
    value_type: str
    note: str | None
    updated_at: datetime


class ValueAssessmentOut(BaseModel):
    status: str
    label_ar: str
    message_ar: str


class ValueWithMetaOut(ValueOut):
    assessment: ValueAssessmentOut


class PeriodDetailOut(BaseModel):
    period: PeriodOut
    values: list[ValueWithMetaOut]


class StatusChangeRequest(BaseModel):
    note: str | None = None


class RevisionOut(ORMModel):
    id: uuid.UUID
    value_id: uuid.UUID
    action: str
    old_value: float | None
    new_value: float | None
    note: str | None
    actor_user_id: uuid.UUID | None
    at: datetime


# ---- Sync (v0.6) ----
class SyncOperation(BaseModel):
    op_id: str = Field(min_length=1, max_length=128)
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=128)
    op: str = Field(default="upsert", pattern="^(upsert|delete)$")
    base_rev: int = Field(default=0, ge=0)
    payload: dict = Field(default_factory=dict)


class SyncPushRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    hospital_id: uuid.UUID | None = None
    batch_id: str = Field(min_length=1, max_length=128)
    sent_at: datetime | None = None
    operations: list[SyncOperation] = Field(default_factory=list, max_length=500)


class SyncOpResult(BaseModel):
    op_id: str
    status: str  # applied | conflict | rejected
    new_rev: int | None = None
    current_rev: int | None = None
    server_payload: dict | None = None
    reason: str | None = None
    message_ar: str | None = None


class SyncPushResponse(BaseModel):
    batch_id: str
    server_seq: int
    results: list[SyncOpResult]


class SyncChange(BaseModel):
    server_seq: int
    entity_type: str
    entity_id: str
    op: str
    rev: int
    hospital_id: uuid.UUID | None = None
    payload: dict | None = None


class SyncPullResponse(BaseModel):
    from_seq: int
    to_seq: int
    has_more: bool
    changes: list[SyncChange]


class SyncBootstrapResponse(BaseModel):
    server_seq: int
    hospital_id: uuid.UUID | None = None
    node_id: str
    indicators: list[dict]
    assignments: list[dict]
    periods: list[dict]
    departments: list[dict]
    incidents: list[dict] = Field(default_factory=list)
    capa_actions: list[dict] = Field(default_factory=list)
    risks: list[dict] = Field(default_factory=list)
    audits: list[dict] = Field(default_factory=list)
    improvement_plans: list[dict] = Field(default_factory=list)
    improvement_actions: list[dict] = Field(default_factory=list)


class SyncStatusResponse(BaseModel):
    node_id: str | None = None
    hospital_id: uuid.UUID | None = None
    last_seq: int
    server_seq: int
    pending_remote: int
    last_seen_at: datetime | None = None


# ---- v0.7: quality and patient safety ------------------------------------


class IncidentCreate(BaseModel):
    hospital_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    incident_type: str = Field(
        default="other",
        pattern="^(medication|fall|pressure_ulcer|infection|surgical|diagnostic|transfusion|equipment|behaviour|other)$",
    )
    severity: str = Field(
        default="moderate", pattern="^(near_miss|minor|moderate|major|catastrophic)$"
    )
    patient_harm: str = Field(default="none", pattern="^(none|mild|moderate|severe|death)$")
    occurred_at: datetime | None = None
    is_anonymous: bool = False
    immediate_action: str | None = Field(default=None, max_length=8000)


class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    department_id: uuid.UUID | None = None
    incident_type: str | None = None
    severity: str | None = None
    patient_harm: str | None = None
    occurred_at: datetime | None = None
    immediate_action: str | None = Field(default=None, max_length=8000)


class IncidentStatusChange(BaseModel):
    status: str = Field(pattern="^(reported|under_review|rca|capa|closed|rejected)$")
    note: str | None = Field(default=None, max_length=2000)


class IncidentOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    department_id: uuid.UUID | None
    code: str
    title: str
    description: str | None
    incident_type: str
    severity: str
    patient_harm: str
    occurred_at: datetime | None
    reported_at: datetime
    is_anonymous: bool
    status: str
    immediate_action: str | None
    closed_at: datetime | None
    rev: int
    created_at: datetime
    updated_at: datetime


class RcaCreate(BaseModel):
    method: str = Field(default="five_whys", pattern="^(five_whys|fishbone|fault_tree|other)$")
    team_ar: str | None = Field(default=None, max_length=2000)
    timeline_ar: str | None = Field(default=None, max_length=20000)
    findings_ar: str | None = Field(default=None, max_length=20000)


class RcaUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|completed|cancelled)$")
    method: str | None = None
    team_ar: str | None = Field(default=None, max_length=2000)
    timeline_ar: str | None = Field(default=None, max_length=20000)
    findings_ar: str | None = Field(default=None, max_length=20000)


class RcaCauseCreate(BaseModel):
    category: str = Field(
        default="other",
        pattern="^(patient|staff|communication|equipment|environment|process|management|training|other)$",
    )
    description_ar: str = Field(min_length=3, max_length=4000)
    is_root_cause: bool = False


class RcaCauseOut(ORMModel):
    id: uuid.UUID
    rca_id: uuid.UUID
    category: str
    description_ar: str
    is_root_cause: bool
    created_at: datetime


class RcaOut(ORMModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    hospital_id: uuid.UUID
    status: str
    method: str
    team_ar: str | None
    timeline_ar: str | None
    findings_ar: str | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RcaDetailOut(BaseModel):
    rca: RcaOut
    causes: list[RcaCauseOut]


class CapaCreate(BaseModel):
    hospital_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    rca_id: uuid.UUID | None = None
    audit_id: uuid.UUID | None = None
    kind: str = Field(default="corrective", pattern="^(corrective|preventive)$")
    title: str = Field(min_length=3, max_length=300)
    description_ar: str | None = Field(default=None, max_length=8000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


class CapaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description_ar: str | None = Field(default=None, max_length=8000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    priority: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")
    status: str | None = Field(default=None, pattern="^(open|in_progress|done|verified|cancelled)$")
    completion_note_ar: str | None = Field(default=None, max_length=4000)


class CapaOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    department_id: uuid.UUID | None
    incident_id: uuid.UUID | None
    rca_id: uuid.UUID | None
    audit_id: uuid.UUID | None
    kind: str
    title: str
    description_ar: str | None
    owner_name_ar: str | None
    due_date: date | None
    priority: str
    status: str
    completion_note_ar: str | None
    completed_at: datetime | None
    verified_at: datetime | None
    is_overdue: bool = False
    created_at: datetime
    updated_at: datetime


class RiskCreate(BaseModel):
    hospital_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    code: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=3, max_length=300)
    description_ar: str | None = Field(default=None, max_length=8000)
    category: str = Field(
        default="clinical",
        pattern="^(clinical|medication|infection|environment|equipment|staffing|information|security|other)$",
    )
    likelihood: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    mitigation_ar: str | None = Field(default=None, max_length=8000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    review_date: date | None = None


class RiskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description_ar: str | None = Field(default=None, max_length=8000)
    category: str | None = None
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    mitigation_ar: str | None = Field(default=None, max_length=8000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    review_date: date | None = None
    status: str | None = Field(default=None, pattern="^(open|mitigated|accepted|closed)$")


class RiskOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    department_id: uuid.UUID | None
    code: str
    title: str
    description_ar: str | None
    category: str
    likelihood: int
    impact: int
    score: int
    mitigation_ar: str | None
    owner_name_ar: str | None
    review_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime


class AuditCreate(BaseModel):
    hospital_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    code: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=3, max_length=300)
    standard_ar: str | None = Field(default=None, max_length=300)
    scope_ar: str | None = Field(default=None, max_length=4000)
    auditor_name_ar: str | None = Field(default=None, max_length=200)
    audit_date: date | None = None


class AuditUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    standard_ar: str | None = Field(default=None, max_length=300)
    scope_ar: str | None = Field(default=None, max_length=4000)
    auditor_name_ar: str | None = Field(default=None, max_length=200)
    audit_date: date | None = None
    status: str | None = Field(default=None, pattern="^(planned|in_progress|completed|closed)$")
    score: float | None = Field(default=None, ge=0, le=100)
    findings_ar: str | None = Field(default=None, max_length=20000)


class AuditOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    department_id: uuid.UUID | None
    code: str
    title: str
    standard_ar: str | None
    scope_ar: str | None
    auditor_name_ar: str | None
    audit_date: date | None
    status: str
    score: float | None
    findings_ar: str | None
    created_at: datetime
    updated_at: datetime


class ImprovementPlanCreate(BaseModel):
    hospital_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    code: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=3, max_length=300)
    objective_ar: str | None = Field(default=None, max_length=4000)
    baseline_ar: str | None = Field(default=None, max_length=4000)
    target_ar: str | None = Field(default=None, max_length=4000)
    indicator_id: uuid.UUID | None = None
    owner_name_ar: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    due_date: date | None = None


class ImprovementPlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    objective_ar: str | None = Field(default=None, max_length=4000)
    baseline_ar: str | None = Field(default=None, max_length=4000)
    target_ar: str | None = Field(default=None, max_length=4000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    due_date: date | None = None
    status: str | None = Field(default=None, pattern="^(draft|active|completed|cancelled)$")


class ImprovementPlanOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    department_id: uuid.UUID | None
    code: str
    title: str
    objective_ar: str | None
    baseline_ar: str | None
    target_ar: str | None
    indicator_id: uuid.UUID | None
    owner_name_ar: str | None
    start_date: date | None
    due_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime


class ImprovementActionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    note_ar: str | None = Field(default=None, max_length=4000)


class ImprovementActionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    status: str | None = Field(default=None, pattern="^(open|in_progress|done|cancelled)$")
    note_ar: str | None = Field(default=None, max_length=4000)


class ImprovementActionOut(ORMModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    title: str
    owner_name_ar: str | None
    due_date: date | None
    status: str
    note_ar: str | None
    created_at: datetime
    updated_at: datetime


class ImprovementPlanDetailOut(BaseModel):
    plan: ImprovementPlanOut
    actions: list[ImprovementActionOut]


class DocumentCreate(BaseModel):
    hospital_id: uuid.UUID | None = None
    code: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=3, max_length=300)
    doc_type: str = Field(
        default="policy", pattern="^(policy|procedure|guideline|form|record|other)$"
    )
    version: str = Field(default="1.0", max_length=20)
    summary_ar: str | None = Field(default=None, max_length=8000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    effective_date: date | None = None
    review_date: date | None = None


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    doc_type: str | None = None
    summary_ar: str | None = Field(default=None, max_length=8000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    effective_date: date | None = None
    review_date: date | None = None
    status: str | None = Field(default=None, pattern="^(draft|under_review|approved|obsolete)$")


class DocumentOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    code: str
    title: str
    doc_type: str
    version: str
    status: str
    summary_ar: str | None
    owner_name_ar: str | None
    effective_date: date | None
    review_date: date | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MeetingCreate(BaseModel):
    hospital_id: uuid.UUID | None = None
    title: str = Field(min_length=3, max_length=300)
    meeting_date: date | None = None
    location_ar: str | None = Field(default=None, max_length=200)
    chair_name_ar: str | None = Field(default=None, max_length=200)
    attendees_ar: str | None = Field(default=None, max_length=4000)
    agenda_ar: str | None = Field(default=None, max_length=8000)
    minutes_ar: str | None = Field(default=None, max_length=20000)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    meeting_date: date | None = None
    location_ar: str | None = Field(default=None, max_length=200)
    chair_name_ar: str | None = Field(default=None, max_length=200)
    attendees_ar: str | None = Field(default=None, max_length=4000)
    agenda_ar: str | None = Field(default=None, max_length=8000)
    minutes_ar: str | None = Field(default=None, max_length=20000)
    status: str | None = Field(default=None, pattern="^(scheduled|held|cancelled)$")


class MeetingDecisionCreate(BaseModel):
    decision_ar: str = Field(min_length=3, max_length=4000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    due_date: date | None = None


class MeetingDecisionUpdate(BaseModel):
    decision_ar: str | None = Field(default=None, min_length=3, max_length=4000)
    owner_name_ar: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    status: str | None = Field(default=None, pattern="^(open|in_progress|done|cancelled)$")


class MeetingDecisionOut(ORMModel):
    id: uuid.UUID
    meeting_id: uuid.UUID
    decision_ar: str
    owner_name_ar: str | None
    due_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime


class MeetingOut(ORMModel):
    id: uuid.UUID
    hospital_id: uuid.UUID
    title: str
    meeting_date: date | None
    location_ar: str | None
    chair_name_ar: str | None
    attendees_ar: str | None
    agenda_ar: str | None
    minutes_ar: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class MeetingDetailOut(BaseModel):
    meeting: MeetingOut
    decisions: list[MeetingDecisionOut]


class QualitySummaryOut(BaseModel):
    """Hospital quality dashboard: real counts from the stored rows."""

    hospital_id: uuid.UUID
    incidents_total: int
    incidents_open: int
    incidents_by_severity: dict[str, int]
    incidents_by_type: dict[str, int]
    rca_open: int
    capa_total: int
    capa_open: int
    capa_overdue: int
    risks_total: int
    risks_high: int
    audits_total: int
    audits_completed: int
    plans_active: int
    documents_approved: int
    meetings_held: int
    decisions_open: int


# ---- Assistant (v0.8) ----
class InsightOut(BaseModel):
    """One finding, with the numbers it was computed from."""

    kind: str
    severity: str
    title_ar: str
    detail_ar: str
    basis: dict = Field(default_factory=dict)
    hospital_id: uuid.UUID | None = None
    indicator_id: uuid.UUID | None = None


class ImprovementAreaOut(BaseModel):
    indicator_code: str
    indicator_name_ar: str
    department_name_ar: str | None = None
    value: float | None = None
    unit_ar: str | None = None
    target_value: float | None = None
    assessment_status: str
    assessment_label_ar: str
    movement: str


class HospitalInsightOut(BaseModel):
    hospital_id: uuid.UUID
    hospital_name_ar: str
    year: int
    month: int | None = None
    period_status: str | None = None
    compliance_percent: float | None = None
    indicators_with_value: int
    indicators_met: int
    indicators_at_risk: int
    insights: list[InsightOut]
    improvement_areas: list[ImprovementAreaOut]
    disclaimer_ar: str
    generated_at: str
    narrative_ar: str | None = None


class NationalInsightOut(BaseModel):
    year: int
    month: int | None = None
    hospitals_total: int
    hospitals_reported: int
    compliance_percent: float | None = None
    insights: list[InsightOut]
    disclaimer_ar: str
    generated_at: str
    narrative_ar: str | None = None


class DraftReportOut(BaseModel):
    hospital_id: uuid.UUID
    hospital_name_ar: str
    year: int
    month: int | None = None
    report_text_ar: str
    disclaimer_ar: str
    generated_at: str


class AssistantStatusOut(BaseModel):
    enabled: bool
    model_configured: bool
    narrative_available: bool
    note_ar: str


# ---- Alerts (v0.9) ----
class AlertOut(BaseModel):
    """One computed alert, with its acknowledgement state."""

    key: str
    kind: str
    source: str
    source_label_ar: str
    severity: str
    title_ar: str
    detail_ar: str
    hospital_id: uuid.UUID | None = None
    hospital_name_ar: str | None = None
    period_year: int
    period_month: int | None = None
    basis: dict = Field(default_factory=dict)
    acked: bool = False
    acked_by_name: str | None = None
    acked_at: str | None = None
    note_ar: str | None = None


class AlertSummaryOut(BaseModel):
    total: int
    high: int
    medium: int
    info: int
    unacknowledged: int
    by_source: dict[str, int] = Field(default_factory=dict)


class AlertListOut(BaseModel):
    year: int
    month: int | None = None
    scope: str
    summary: AlertSummaryOut
    alerts: list[AlertOut]


class AlertAckRequest(BaseModel):
    note_ar: str | None = Field(default=None, max_length=500)


# ---- Alert rules (v0.10) ----
class AlertParamSpecOut(BaseModel):
    key: str
    label_ar: str
    type: str
    min: float
    max: float
    step: float
    unit_ar: str = ""


class AlertRuleOut(BaseModel):
    kind: str
    label_ar: str
    description_ar: str
    applies_to: str  # "national" | "both"
    enabled: bool
    effective_params: dict
    national_params: dict
    hospital_params: dict | None = None
    hospital_override: bool
    params_spec: list[AlertParamSpecOut]


class AlertRuleCatalogueOut(BaseModel):
    hospital_id: uuid.UUID | None = None
    scope: str  # "national" | "hospital"
    rules: list[AlertRuleOut]
    note_ar: str


class AlertRuleUpdate(BaseModel):
    params: dict = Field(default_factory=dict)
    is_enabled: bool = True
    note_ar: str | None = Field(default=None, max_length=500)


# ---- Audit log (v0.11) ----
class AuditEntryOut(BaseModel):
    id: str
    at: datetime
    entity_type: str
    entity_label_ar: str
    entity_id: str
    action: str
    action_label_ar: str
    summary_ar: str
    actor_user_id: str | None = None
    actor_name: str | None = None
    actor_username: str | None = None
    hospital_id: str | None = None
    hospital_name_ar: str | None = None
    node: str | None = None
    before: dict | None = None
    after: dict | None = None


class AuditLogPageOut(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[AuditEntryOut]


class AuditFacetItemOut(BaseModel):
    code: str
    label_ar: str
    count: int


class AuditActorFacetOut(BaseModel):
    user_id: str
    name: str
    username: str | None = None
    count: int


class AuditFacetsOut(BaseModel):
    entity_types: list[AuditFacetItemOut]
    actions: list[AuditFacetItemOut]
    actors: list[AuditActorFacetOut]


# ---- National sync monitor (v0.12) ----
class SyncDeviceOut(BaseModel):
    node_id: str
    hospital_id: str | None = None
    hospital_name_ar: str | None = None
    name: str | None = None
    last_seq: int
    last_seen_at: datetime | None = None
    days_since_seen: int | None = None
    status: str  # "ok" | "stale"
    status_label_ar: str


class SyncConflictOut(BaseModel):
    id: str
    entity_type: str
    entity_label_ar: str
    entity_id: str
    node_id: str | None = None
    hospital_id: str | None = None
    hospital_name_ar: str | None = None
    resolution: str
    resolution_label_ar: str
    resolved_by: str | None = None
    resolved_by_name: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    local_payload: dict | None = None
    server_payload: dict | None = None


class SyncConflictPageOut(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[SyncConflictOut]


class SyncMonitorOverviewOut(BaseModel):
    devices_total: int
    devices_ok: int
    devices_stale: int
    open_conflicts: int
    resolved_conflicts: int
    stale_days: int


class SyncConflictResolve(BaseModel):
    resolution: str = Field(pattern="^(reviewed|dismissed)$")
    note_ar: str | None = Field(default=None, max_length=500)
