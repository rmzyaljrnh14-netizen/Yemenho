// Bridge to the Tauri desktop shell (v0.6).
//
// The offline store lives in Rust; this module is the only place the web code
// talks to it. When the app runs in a browser (dev/preview) there is no native
// layer, so every call degrades to `null`/no-op and the app behaves exactly as
// before (online only).

export interface LocalStatus {
  node_id: string;
  hospital_id: string | null;
  cursor: number;
  pending_count: number;
  failed_count: number;
  conflict_count: number;
  last_sync_at: string | null;
  db_path: string;
}

export interface PendingOp {
  op_id: string;
  entity_type: string;
  entity_id: string;
  op: string;
  base_rev: number;
  payload: Record<string, unknown>;
  attempts: number;
  state: string;
  last_error: string | null;
}

export interface LocalConflict {
  id: string;
  entity_type: string;
  entity_id: string;
  resolution: string;
  created_at: string;
}

export interface SaveValueInput {
  period_id: string;
  indicator_id: string;
  department_id?: string | null;
  numerator?: number | null;
  denominator?: number | null;
  entered_value?: number | null;
  computation: string;
  multiplier?: number | null;
  direction: string;
  target_value?: number | null;
  acceptable_min?: number | null;
  acceptable_max?: number | null;
  note?: string | null;
  value_id?: string | null;
}

export interface SaveIncidentInput {
  incident_id: string;
  hospital_id: string;
  department_id?: string | null;
  title: string;
  description?: string | null;
  incident_type: string;
  severity: string;
  patient_harm: string;
  occurred_at?: string | null;
  is_anonymous?: boolean;
  immediate_action?: string | null;
}

export interface SaveCapaInput {
  capa_id: string;
  hospital_id: string;
  department_id?: string | null;
  incident_id?: string | null;
  kind: string;
  title: string;
  description_ar?: string | null;
  owner_name_ar?: string | null;
  due_date?: string | null;
  priority: string;
}

export interface SaveRiskInput {
  risk_id: string;
  hospital_id: string;
  department_id?: string | null;
  title: string;
  description_ar?: string | null;
  category: string;
  likelihood: number;
  impact: number;
  mitigation_ar?: string | null;
  owner_name_ar?: string | null;
  review_date?: string | null;
}

export interface SaveAuditInput {
  audit_id: string;
  hospital_id: string;
  department_id?: string | null;
  title: string;
  standard_ar?: string | null;
  scope_ar?: string | null;
  auditor_name_ar?: string | null;
  audit_date?: string | null;
}

export interface SavePlanInput {
  plan_id: string;
  hospital_id: string;
  department_id?: string | null;
  title: string;
  objective_ar?: string | null;
  baseline_ar?: string | null;
  target_ar?: string | null;
  owner_name_ar?: string | null;
  start_date?: string | null;
  due_date?: string | null;
}

export interface SavePlanActionInput {
  action_id: string;
  plan_id: string;
  title: string;
  owner_name_ar?: string | null;
  due_date?: string | null;
  note_ar?: string | null;
}

type InvokeFn = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

function getInvoke(): InvokeFn | null {
  const w = window as unknown as { __TAURI__?: { core?: { invoke?: InvokeFn } } };
  const fn = w.__TAURI__?.core?.invoke;
  return typeof fn === "function" ? fn : null;
}

export function isDesktop(): boolean {
  return getInvoke() !== null;
}

async function call<T>(cmd: string, args?: Record<string, unknown>): Promise<T | null> {
  const invoke = getInvoke();
  if (!invoke) return null;
  try {
    return (await invoke(cmd, args)) as T;
  } catch (e) {
    // The native layer must never crash the UI; surface it as a null result and
    // let the caller fall back to online behaviour.
    console.warn(`desktop invoke ${cmd} failed`, e);
    return null;
  }
}

export const desktop = {
  localStatus: () => call<LocalStatus>("local_status"),
  setHospital: (hospital_id: string) => call<void>("set_hospital", { hospitalId: hospital_id }),
  setCursor: (seq: number) => call<void>("set_cursor", { seq }),
  markSynced: (at?: string) => call<void>("mark_synced", { at: at ?? null }),
  saveValue: (input: SaveValueInput) => call<Record<string, unknown>>("save_value", { input }),
  listValues: (period_id: string) => call<Record<string, unknown>[]>("list_values", { periodId: period_id }),
  saveIncident: (input: SaveIncidentInput) =>
    call<Record<string, unknown>>("save_incident", {
      incidentId: input.incident_id,
      hospitalId: input.hospital_id,
      departmentId: input.department_id ?? null,
      title: input.title,
      description: input.description ?? null,
      incidentType: input.incident_type,
      severity: input.severity,
      patientHarm: input.patient_harm,
      occurredAt: input.occurred_at ?? null,
      isAnonymous: input.is_anonymous ?? false,
      immediateAction: input.immediate_action ?? null,
    }),
  listIncidents: (hospital_id?: string | null) =>
    call<Record<string, unknown>[]>("list_incidents", { hospitalId: hospital_id ?? null }),
  saveCapa: (input: SaveCapaInput) =>
    call<Record<string, unknown>>("save_capa", {
      capaId: input.capa_id,
      hospitalId: input.hospital_id,
      departmentId: input.department_id ?? null,
      incidentId: input.incident_id ?? null,
      kind: input.kind,
      title: input.title,
      descriptionAr: input.description_ar ?? null,
      ownerNameAr: input.owner_name_ar ?? null,
      dueDate: input.due_date ?? null,
      priority: input.priority,
    }),
  listCapa: (hospital_id?: string | null) =>
    call<Record<string, unknown>[]>("list_capa", { hospitalId: hospital_id ?? null }),
  saveRisk: (input: SaveRiskInput) =>
    call<Record<string, unknown>>("save_risk", {
      riskId: input.risk_id,
      hospitalId: input.hospital_id,
      departmentId: input.department_id ?? null,
      title: input.title,
      descriptionAr: input.description_ar ?? null,
      category: input.category,
      likelihood: input.likelihood,
      impact: input.impact,
      mitigationAr: input.mitigation_ar ?? null,
      ownerNameAr: input.owner_name_ar ?? null,
      reviewDate: input.review_date ?? null,
    }),
  listRisks: (hospital_id?: string | null) =>
    call<Record<string, unknown>[]>("list_risks", { hospitalId: hospital_id ?? null }),
  saveAudit: (input: SaveAuditInput) =>
    call<Record<string, unknown>>("save_audit", {
      auditId: input.audit_id,
      hospitalId: input.hospital_id,
      departmentId: input.department_id ?? null,
      title: input.title,
      standardAr: input.standard_ar ?? null,
      scopeAr: input.scope_ar ?? null,
      auditorNameAr: input.auditor_name_ar ?? null,
      auditDate: input.audit_date ?? null,
    }),
  listAudits: (hospital_id?: string | null) =>
    call<Record<string, unknown>[]>("list_audits", { hospitalId: hospital_id ?? null }),
  savePlan: (input: SavePlanInput) =>
    call<Record<string, unknown>>("save_plan", {
      planId: input.plan_id,
      hospitalId: input.hospital_id,
      departmentId: input.department_id ?? null,
      title: input.title,
      objectiveAr: input.objective_ar ?? null,
      baselineAr: input.baseline_ar ?? null,
      targetAr: input.target_ar ?? null,
      ownerNameAr: input.owner_name_ar ?? null,
      startDate: input.start_date ?? null,
      dueDate: input.due_date ?? null,
    }),
  listPlans: (hospital_id?: string | null) =>
    call<Record<string, unknown>[]>("list_plans", { hospitalId: hospital_id ?? null }),
  savePlanAction: (input: SavePlanActionInput) =>
    call<Record<string, unknown>>("save_plan_action", {
      actionId: input.action_id,
      planId: input.plan_id,
      title: input.title,
      ownerNameAr: input.owner_name_ar ?? null,
      dueDate: input.due_date ?? null,
      noteAr: input.note_ar ?? null,
    }),
  listPlanActions: (plan_id?: string | null) =>
    call<Record<string, unknown>[]>("list_plan_actions", { planId: plan_id ?? null }),
  createPeriod: (args: {
    period_id: string;
    hospital_id: string;
    period_type: string;
    year: number;
    month?: number | null;
    quarter?: number | null;
  }) =>
    call<Record<string, unknown>>("create_period", {
      periodId: args.period_id,
      hospitalId: args.hospital_id,
      periodType: args.period_type,
      year: args.year,
      month: args.month ?? null,
      quarter: args.quarter ?? null,
    }),
  listPeriods: (hospital_id?: string | null) =>
    call<Record<string, unknown>[]>("list_periods", { hospitalId: hospital_id ?? null }),
  cacheDepartments: (departments: unknown[]) => call<number>("cache_departments", { departments }),
  listDepartments: () => call<Record<string, unknown>[]>("list_departments"),
  cacheHospitals: (hospitals: unknown[]) => call<number>("cache_hospitals", { hospitals }),
  listHospitals: () => call<Record<string, unknown>[]>("list_hospitals"),
  cacheAssignments: (assignments: unknown[]) => call<number>("cache_assignments", { assignments }),
  listAssignments: () => call<Record<string, unknown>[]>("list_assignments"),
  pendingOps: (include_failed = false) => call<PendingOp[]>("pending_ops", { includeFailed: include_failed }),
  outboxAck: (op_id: string, status: string, new_rev: number | null, error: string | null) =>
    call<void>("outbox_ack", { opId: op_id, status, newRev: new_rev, error }),
  bumpAttempts: (op_id: string, error: string) => call<void>("bump_attempts", { opId: op_id, error }),
  applyPull: (changes: unknown[], to_seq: number) => call<number>("apply_pull", { changes, toSeq: to_seq }),
  cacheLibrary: (indicators: unknown[]) => call<number>("cache_library", { indicators }),
  localLibrary: () => call<Record<string, unknown>[]>("local_library"),
  recordConflict: (
    op_id: string,
    entity_type: string,
    entity_id: string,
    local_payload: unknown,
    server_payload: unknown,
  ) => call<void>("record_conflict", { opId: op_id, entityType: entity_type, entityId: entity_id, localPayload: local_payload, serverPayload: server_payload }),
  listConflicts: () => call<LocalConflict[]>("list_conflicts"),
  exportBackup: () => call<Record<string, unknown>>("export_backup"),
};
