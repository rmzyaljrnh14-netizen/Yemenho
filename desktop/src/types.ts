// Types mirroring the backend API (v0.1).

export interface ScopeOrg {
  level: string;
  hospital_id: string | null;
  governorate_id: string | null;
}

export interface Me {
  id: string;
  username: string;
  display_name: string;
  is_active: boolean;
  roles: string[];
  scopes: string[];
  scope_org: ScopeOrg;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

export interface Organization {
  id: string;
  parent_id: string | null;
  level: "central" | "governorate" | "district" | "hospital";
  name_ar: string;
  code: string | null;
}

export interface Hospital {
  id: string;
  name_ar: string;
  code: string;
  governorate_id: string | null;
  organization_id: string | null;
  is_active: boolean;
}

export interface Department {
  id: string;
  hospital_id: string;
  name_ar: string;
  code: string | null;
  is_active: boolean;
}

export interface UserOut {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  at: string;
  entity_type: string;
  entity_label_ar: string;
  entity_id: string;
  action: string;
  action_label_ar: string;
  summary_ar: string;
  actor_user_id: string | null;
  actor_name: string | null;
  actor_username: string | null;
  hospital_id: string | null;
  hospital_name_ar: string | null;
  node: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface AuditLogPage {
  total: number;
  limit: number;
  offset: number;
  entries: AuditEntry[];
}

export interface AuditFacetItem {
  code: string;
  label_ar: string;
  count: number;
}

export interface AuditActorFacet {
  user_id: string;
  name: string;
  username: string | null;
  count: number;
}

export interface AuditFacets {
  entity_types: AuditFacetItem[];
  actions: AuditFacetItem[];
  actors: AuditActorFacet[];
}

export interface ApiErrorBody {
  detail?: { code: string; message_ar: string };
  error?: { code: string; message_ar: string };
}

// ---- v0.4: indicators and reporting ----
export type Computation = "ratio" | "rate" | "percent" | "count" | "average" | "sum" | "entered";
export type Direction = "higher_better" | "lower_better" | "target_range";
export type Frequency = "monthly" | "quarterly" | "semi_annual" | "annual";
export type PeriodStatus = "draft" | "submitted" | "reviewed" | "approved" | "returned";

export interface Indicator {
  id: string;
  code: string;
  name_ar: string;
  definition_ar: string | null;
  purpose_ar: string | null;
  calculation_ar: string | null;
  computation: Computation;
  unit_ar: string | null;
  data_source_ar: string | null;
  frequency: Frequency;
  responsible_party_ar: string | null;
  direction: Direction;
  target_value: number | null;
  acceptable_min: number | null;
  acceptable_max: number | null;
  multiplier: number;
  numerator_label_ar: string | null;
  denominator_label_ar: string | null;
  is_active: boolean;
}

export interface AssignedIndicator {
  assignment_id: string;
  indicator: Indicator;
  department_id: string | null;
  target_override: number | null;
}

export interface ReportingPeriod {
  id: string;
  hospital_id: string;
  period_type: "monthly" | "quarterly" | "annual";
  year: number;
  month: number | null;
  quarter: number | null;
  status: PeriodStatus;
  note: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  approved_at: string | null;
  returned_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IndicatorValue {
  id: string;
  period_id: string;
  indicator_id: string;
  department_id: string | null;
  numerator: number | null;
  denominator: number | null;
  value: number | null;
  value_type: "computed" | "entered";
  note: string | null;
  updated_at: string;
}

export interface Assessment {
  status: "good" | "warning" | "poor" | "unknown";
  label_ar: string;
  message_ar: string;
}

export interface ValueWithMeta extends IndicatorValue {
  assessment: Assessment;
}

export interface PeriodDetail {
  period: ReportingPeriod;
  values: ValueWithMeta[];
}

// ---- v0.5: reports, dashboards and exports ----
export type AssessmentStatus = "good" | "warning" | "poor" | "unknown";
export type Movement = "up" | "down" | "flat" | "unknown";

export interface HospitalReportPoint {
  indicator_id: string;
  code: string;
  name_ar: string;
  direction: Direction;
  unit_ar: string | null;
  target_value: number | null;
  value: number | null;
  assessment_status: AssessmentStatus;
  assessment_label_ar: string;
  movement: Movement;
  improving: boolean | null;
  department_id: string | null;
  department_name_ar: string | null;
}

export interface HospitalReport {
  hospital_id: string;
  hospital_name_ar: string;
  period_id: string | null;
  period_status: PeriodStatus | null;
  indicators_total: number;
  indicators_with_value: number;
  indicators_met: number;
  indicators_at_risk: number;
  indicators_unknown: number;
  compliance_percent: number | null;
  points: HospitalReportPoint[];
}

export interface HospitalOverviewRow {
  hospital_id: string;
  hospital_name_ar: string;
  governorate_name_ar: string | null;
  reported: boolean;
  period_status: PeriodStatus | null;
  last_sync_label: string;
  indicators_with_value: number;
  indicators_met: number;
  indicators_at_risk: number;
  compliance_percent: number | null;
}

export interface GovernorateRow {
  governorate_name_ar: string;
  hospitals: number;
  reported: number;
  met: number;
  with_value: number;
  compliance_percent: number | null;
}

export interface NationalOverview {
  year: number;
  month: number | null;
  hospitals_total: number;
  hospitals_reported: number;
  indicators_total: number;
  indicators_with_value: number;
  indicators_met: number;
  indicators_at_risk: number;
  compliance_percent: number | null;
  average_hospital_compliance: number | null;
  hospitals: HospitalOverviewRow[];
  governorates: GovernorateRow[];
}

export interface TrendPoint {
  period_label: string;
  year: number;
  month: number | null;
  value: number | null;
}

export interface TrendResponse {
  indicator_id: string;
  hospital_id: string;
  points: TrendPoint[];
}

export interface CompareRow {
  hospital_id: string;
  hospital_name_ar: string;
  governorate_name_ar: string | null;
  reported: boolean;
  period_status: PeriodStatus | null;
  compliance_percent: number | null;
  indicators_met: number;
  indicators_with_value: number;
}

export interface CompareResponse {
  year: number;
  month: number | null;
  hospitals: CompareRow[];
}

export interface LateHospital {
  hospital_id: string;
  hospital_name_ar: string;
  governorate_name_ar: string | null;
  period_status: string;
  status_label_ar: string;
}

export interface LateResponse {
  year: number;
  month: number | null;
  hospitals: LateHospital[];
}

// ---- v0.6: offline sync ----
export interface SyncChange {
  server_seq: number;
  entity_type: string;
  entity_id: string;
  op: string;
  rev: number;
  hospital_id: string | null;
  payload: Record<string, unknown> | null;
}

export interface SyncPullResponse {
  from_seq: number;
  to_seq: number;
  has_more: boolean;
  changes: SyncChange[];
}

export interface SyncOpResult {
  op_id: string;
  status: "applied" | "conflict" | "rejected";
  new_rev?: number | null;
  current_rev?: number | null;
  server_payload?: Record<string, unknown> | null;
  reason?: string | null;
  message_ar?: string | null;
}

export interface SyncPushResponse {
  batch_id: string;
  server_seq: number;
  results: SyncOpResult[];
}

export interface SyncBootstrapResponse {
  server_seq: number;
  hospital_id: string | null;
  node_id: string;
  indicators: Record<string, unknown>[];
  assignments: Record<string, unknown>[];
  periods: Record<string, unknown>[];
  departments: Record<string, unknown>[];
  incidents?: Record<string, unknown>[];
}

export interface SyncStatusResponse {
  node_id: string | null;
  hospital_id: string | null;
  last_seq: number;
  server_seq: number;
  pending_remote: number;
  last_seen_at: string | null;
}

// ---- v0.7: quality and patient safety ----
export type IncidentType =
  | "medication" | "fall" | "pressure_ulcer" | "infection" | "surgical"
  | "diagnostic" | "transfusion" | "equipment" | "behaviour" | "other";

export type IncidentSeverity = "near_miss" | "minor" | "moderate" | "major" | "catastrophic";
export type PatientHarm = "none" | "mild" | "moderate" | "severe" | "death";
export type IncidentStatus =
  | "reported" | "under_review" | "rca" | "capa" | "closed" | "rejected";

export interface Incident {
  id: string;
  hospital_id: string;
  department_id: string | null;
  code: string;
  title: string;
  description: string | null;
  incident_type: IncidentType;
  severity: IncidentSeverity;
  patient_harm: PatientHarm;
  occurred_at: string | null;
  reported_at: string;
  is_anonymous: boolean;
  status: IncidentStatus;
  immediate_action: string | null;
  closed_at: string | null;
  rev: number;
  created_at: string;
  updated_at: string;
}

export interface IncidentCreate {
  hospital_id?: string | null;
  department_id?: string | null;
  title: string;
  description?: string | null;
  incident_type: IncidentType;
  severity: IncidentSeverity;
  patient_harm: PatientHarm;
  occurred_at?: string | null;
  is_anonymous?: boolean;
  immediate_action?: string | null;
}

export type CapaKind = "corrective" | "preventive";
export type CapaPriority = "low" | "medium" | "high" | "critical";
export type CapaStatus = "open" | "in_progress" | "done" | "verified" | "cancelled";

export interface CapaAction {
  id: string;
  hospital_id: string;
  department_id: string | null;
  incident_id: string | null;
  rca_id: string | null;
  audit_id: string | null;
  kind: CapaKind;
  title: string;
  description_ar: string | null;
  owner_name_ar: string | null;
  due_date: string | null;
  priority: CapaPriority;
  status: CapaStatus;
  completion_note_ar: string | null;
  is_overdue: boolean;
  synced?: boolean;
}

export interface CapaCreate {
  hospital_id?: string | null;
  department_id?: string | null;
  incident_id?: string | null;
  kind: CapaKind;
  title: string;
  description_ar?: string | null;
  owner_name_ar?: string | null;
  due_date?: string | null;
  priority: CapaPriority;
}

export type RiskCategory =
  | "clinical" | "medication" | "infection" | "environment" | "equipment"
  | "staffing" | "information" | "security" | "other";
export type RiskStatus = "open" | "mitigated" | "accepted" | "closed";

export interface Risk {
  id: string;
  hospital_id: string;
  department_id: string | null;
  code: string;
  title: string;
  description_ar: string | null;
  category: RiskCategory;
  likelihood: number;
  impact: number;
  score: number | null;
  mitigation_ar: string | null;
  owner_name_ar: string | null;
  review_date: string | null;
  status: RiskStatus;
  rev: number;
  synced?: boolean;
}

export interface RiskCreate {
  hospital_id?: string | null;
  department_id?: string | null;
  title: string;
  description_ar?: string | null;
  category: RiskCategory;
  likelihood: number;
  impact: number;
  mitigation_ar?: string | null;
  owner_name_ar?: string | null;
  review_date?: string | null;
}

// ---- Internal audits & improvement plans (v0.15) ----
export type AuditStatus = "planned" | "in_progress" | "completed" | "closed";
export type PlanStatus = "draft" | "active" | "completed" | "cancelled";
export type PlanActionStatus = "open" | "in_progress" | "done" | "cancelled";

export interface QualityAudit {
  id: string;
  hospital_id: string;
  department_id: string | null;
  code: string;
  title: string;
  standard_ar: string | null;
  scope_ar: string | null;
  auditor_name_ar: string | null;
  audit_date: string | null;
  status: AuditStatus;
  score: number | null;
  findings_ar: string | null;
  rev: number;
  synced?: boolean;
}

export interface ImprovementPlan {
  id: string;
  hospital_id: string;
  department_id: string | null;
  code: string;
  title: string;
  objective_ar: string | null;
  baseline_ar: string | null;
  target_ar: string | null;
  indicator_id: string | null;
  owner_name_ar: string | null;
  start_date: string | null;
  due_date: string | null;
  status: PlanStatus;
  rev: number;
  synced?: boolean;
}

export interface ImprovementAction {
  id: string;
  plan_id: string;
  title: string;
  owner_name_ar: string | null;
  due_date: string | null;
  status: PlanActionStatus;
  note_ar: string | null;
  rev: number;
  synced?: boolean;
}

export interface QualitySummary {
  hospital_id: string;
  incidents_total: number;
  incidents_open: number;
  incidents_by_severity: Record<string, number>;
  incidents_by_type: Record<string, number>;
  rca_open: number;
  capa_total: number;
  capa_open: number;
  capa_overdue: number;
  risks_total: number;
  risks_high: number;
  audits_total: number;
  audits_completed: number;
  plans_active: number;
  documents_approved: number;
  meetings_held: number;
  decisions_open: number;
}

// ---- Assistant (v0.8) ----
export interface Insight {
  kind: string;
  severity: "high" | "medium" | "info";
  title_ar: string;
  detail_ar: string;
  basis: Record<string, unknown>;
  hospital_id: string | null;
  indicator_id: string | null;
}

export interface ImprovementArea {
  indicator_code: string;
  indicator_name_ar: string;
  department_name_ar: string | null;
  value: number | null;
  unit_ar: string | null;
  target_value: number | null;
  assessment_status: string;
  assessment_label_ar: string;
  movement: string;
}

export interface HospitalInsight {
  hospital_id: string;
  hospital_name_ar: string;
  year: number;
  month: number | null;
  period_status: string | null;
  compliance_percent: number | null;
  indicators_with_value: number;
  indicators_met: number;
  indicators_at_risk: number;
  insights: Insight[];
  improvement_areas: ImprovementArea[];
  disclaimer_ar: string;
  generated_at: string;
  narrative_ar: string | null;
}

export interface NationalInsight {
  year: number;
  month: number | null;
  hospitals_total: number;
  hospitals_reported: number;
  compliance_percent: number | null;
  insights: Insight[];
  disclaimer_ar: string;
  generated_at: string;
  narrative_ar: string | null;
}

export interface DraftReport {
  hospital_id: string;
  hospital_name_ar: string;
  year: number;
  month: number | null;
  report_text_ar: string;
  disclaimer_ar: string;
  generated_at: string;
}

export interface AssistantStatus {
  enabled: boolean;
  model_configured: boolean;
  narrative_available: boolean;
  note_ar: string;
}

// ---- Alerts (v0.9) ----
export interface Alert {
  key: string;
  kind: string;
  source: "indicators" | "submission" | "quality" | "other";
  source_label_ar: string;
  severity: "high" | "medium" | "info";
  title_ar: string;
  detail_ar: string;
  hospital_id: string | null;
  hospital_name_ar: string | null;
  period_year: number;
  period_month: number | null;
  basis: Record<string, unknown>;
  acked: boolean;
  acked_by_name: string | null;
  acked_at: string | null;
  note_ar: string | null;
}

export interface AlertSummary {
  total: number;
  high: number;
  medium: number;
  info: number;
  unacknowledged: number;
  by_source: Record<string, number>;
}

export interface AlertList {
  year: number;
  month: number | null;
  scope: "national" | "hospital";
  summary: AlertSummary;
  alerts: Alert[];
}

// ---- Alert rules (v0.10) ----
export interface AlertParamSpec {
  key: string;
  label_ar: string;
  type: "int" | "float";
  min: number;
  max: number;
  step: number;
  unit_ar: string;
}

export interface AlertRule {
  kind: string;
  label_ar: string;
  description_ar: string;
  applies_to: "national" | "both";
  enabled: boolean;
  effective_params: Record<string, number>;
  national_params: Record<string, number>;
  hospital_params: Record<string, number> | null;
  hospital_override: boolean;
  params_spec: AlertParamSpec[];
}

export interface AlertRuleCatalogue {
  hospital_id: string | null;
  scope: "national" | "hospital";
  rules: AlertRule[];
  note_ar: string;
}
