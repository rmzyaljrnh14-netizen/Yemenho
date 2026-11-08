// REST client for the central portal. The portal is always online: it talks to
// the backend directly and holds only tokens in the browser.
import type {
  Alert,
  AlertList,
  AlertRule,
  AlertRuleCatalogue,
  AssignedIndicator,
  AssistantStatus,
  AssignmentOut,
  AuditFacets,
  AuditLogPage,
  Capa,
  CompareResponse,
  Department,
  DraftReport,
  Hospital,
  HospitalInsight,
  HospitalReport,
  ImprovementAction,
  ImprovementPlan,
  ImprovementPlanDetail,
  Incident,
  Indicator,
  LateResponse,
  Me,
  MeetingDecision,
  MeetingDetail,
  NationalInsight,
  NationalOverview,
  Organization,
  PeriodDetail,
  QualityAudit,
  QualityDocument,
  QualityMeeting,
  QualitySummary,
  Rca,
  RcaCause,
  RcaDetail,
  ReportingPeriod,
  Revision,
  Risk,
  SyncConflictPage,
  SyncDevice,
  SyncMonitorOverview,
  TokenResponse,
  TrendResponse,
  UserOut,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const ACCESS_KEY = "yhq.portal.access";
const REFRESH_KEY = "yhq.portal.refresh";

export function setTokens(t: TokenResponse | null): void {
  if (t === null) {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  } else {
    localStorage.setItem(ACCESS_KEY, t.access_token);
    localStorage.setItem(REFRESH_KEY, t.refresh_token);
  }
}

export function getAccess(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

function getRefresh(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  const access = getAccess();
  if (access) headers.Authorization = `Bearer ${access}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401 && retry && getRefresh()) {
    if (await tryRefresh()) return request<T>(path, options, false);
  }

  if (!res.ok) {
    let code = "error";
    let message = "حدث خطأ غير متوقع.";
    try {
      const body = await res.json();
      const d = body.detail ?? body.error ?? {};
      code = d.code ?? code;
      message = d.message_ar ?? message;
    } catch {
      /* keep defaults */
    }
    throw new ApiError(res.status, code, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefresh();
  if (!refresh) return false;
  try {
    const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) {
      setTokens(null);
      return false;
    }
    setTokens((await res.json()) as TokenResponse);
    return true;
  } catch {
    return false;
  }
}

export const api = {
  async login(username: string, password: string): Promise<TokenResponse> {
    const t = await request<TokenResponse>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify({ username, password }) },
      false,
    );
    setTokens(t);
    return t;
  },
  logout(): void {
    setTokens(null);
  },
  me: () => request<Me>("/api/v1/auth/me"),

  // ---- organization ----
  organizations: () => request<Organization[]>("/api/v1/organizations"),
  createOrganization: (body: { name_ar: string; level: string; parent_id?: string | null; code?: string }) =>
    request<Organization>("/api/v1/organizations", { method: "POST", body: JSON.stringify(body) }),
  hospitals: () => request<Hospital[]>("/api/v1/hospitals"),
  createHospital: (body: {
    name_ar: string;
    code: string;
    governorate_id?: string | null;
    organization_id?: string | null;
  }) => request<Hospital>("/api/v1/hospitals", { method: "POST", body: JSON.stringify(body) }),
  departments: (hospitalId: string) =>
    request<Department[]>(`/api/v1/hospitals/${hospitalId}/departments`),
  createDepartment: (hospitalId: string, body: { name_ar: string; code?: string; manager_user_id?: string | null }) =>
    request<Department>(`/api/v1/hospitals/${hospitalId}/departments`, {
      method: "POST",
      body: JSON.stringify({ ...body, hospital_id: hospitalId }),
    }),

  // ---- users and access ----
  users: () => request<UserOut[]>("/api/v1/users"),
  createUser: (body: { username: string; display_name: string; password: string; email?: string | null }) =>
    request<UserOut>("/api/v1/users", { method: "POST", body: JSON.stringify(body) }),
  createAssignment: (body: { user_id: string; role_code: string; scope_type: string; scope_id?: string | null }) =>
    request<AssignmentOut>("/api/v1/users/assignments", { method: "POST", body: JSON.stringify(body) }),
  auditLog: (params?: {
    entityType?: string;
    action?: string;
    actorUserId?: string;
    hospitalId?: string;
    since?: string;
    until?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.entityType) qs.set("entity_type", params.entityType);
    if (params?.action) qs.set("action", params.action);
    if (params?.actorUserId) qs.set("actor_user_id", params.actorUserId);
    if (params?.hospitalId) qs.set("hospital_id", params.hospitalId);
    if (params?.since) qs.set("since", params.since);
    if (params?.until) qs.set("until", params.until);
    if (params?.q) qs.set("q", params.q);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const suffix = qs.toString();
    return request<AuditLogPage>(`/api/v1/audit-log${suffix ? `?${suffix}` : ""}`);
  },
  auditFacets: () => request<AuditFacets>("/api/v1/audit-log/facets"),
  exportAuditLog: (
    format: "csv" | "xlsx",
    params?: {
      entityType?: string;
      action?: string;
      actorUserId?: string;
      hospitalId?: string;
      since?: string;
      until?: string;
      q?: string;
    },
  ) => {
    const qs = new URLSearchParams();
    if (params?.entityType) qs.set("entity_type", params.entityType);
    if (params?.action) qs.set("action", params.action);
    if (params?.actorUserId) qs.set("actor_user_id", params.actorUserId);
    if (params?.hospitalId) qs.set("hospital_id", params.hospitalId);
    if (params?.since) qs.set("since", params.since);
    if (params?.until) qs.set("until", params.until);
    if (params?.q) qs.set("q", params.q);
    const suffix = qs.toString();
    return downloadFile(
      `/api/v1/audit-log/export.${format}${suffix ? `?${suffix}` : ""}`,
      `audit-log.${format}`,
    );
  },

  // ---- national sync monitor ----
  syncOverview: () => request<SyncMonitorOverview>("/api/v1/sync-monitor/overview"),
  syncDevices: (onlyStale = false) =>
    request<SyncDevice[]>(`/api/v1/sync-monitor/devices${onlyStale ? "?only_stale=true" : ""}`),
  syncConflicts: (params?: { includeResolved?: boolean; hospitalId?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.includeResolved) qs.set("include_resolved", "true");
    if (params?.hospitalId) qs.set("hospital_id", params.hospitalId);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const suffix = qs.toString();
    return request<SyncConflictPage>(`/api/v1/sync-monitor/conflicts${suffix ? `?${suffix}` : ""}`);
  },
  resolveSyncConflict: (id: string, body: { resolution: "reviewed" | "dismissed"; note_ar?: string | null }) =>
    request<{ id: string; resolution: string }>(`/api/v1/sync-monitor/conflicts/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ---- indicator library ----
  indicators: (search?: string) =>
    request<Indicator[]>(`/api/v1/indicators${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  createIndicator: (body: Partial<Indicator> & { code: string; name_ar: string }) =>
    request<Indicator>("/api/v1/indicators", { method: "POST", body: JSON.stringify(body) }),
  updateIndicator: (id: string, body: Partial<Indicator>) =>
    request<Indicator>(`/api/v1/indicators/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  assignedIndicators: (hospitalId: string, departmentId?: string) =>
    request<AssignedIndicator[]>(
      `/api/v1/hospitals/${hospitalId}/indicators${departmentId ? `?department_id=${departmentId}` : ""}`,
    ),
  assignIndicator: (
    hospitalId: string,
    body: { indicator_id: string; department_id?: string | null; target_override?: number | null },
  ) =>
    request<AssignedIndicator>(`/api/v1/hospitals/${hospitalId}/indicators`, {
      method: "POST",
      body: JSON.stringify({ ...body, hospital_id: hospitalId }),
    }),
  unassignIndicator: (hospitalId: string, assignmentId: string) =>
    request<void>(`/api/v1/hospitals/${hospitalId}/indicators/${assignmentId}`, { method: "DELETE" }),

  // ---- reporting ----
  periods: (hospitalId?: string, year?: number) => {
    const qs = new URLSearchParams();
    if (hospitalId) qs.set("hospital_id", hospitalId);
    if (year) qs.set("year", String(year));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<ReportingPeriod[]>(`/api/v1/periods${suffix}`);
  },
  periodDetail: (periodId: string) => request<PeriodDetail>(`/api/v1/periods/${periodId}`),
  valueRevisions: (valueId: string) => request<Revision[]>(`/api/v1/values/${valueId}/revisions`),
  periodAction: (periodId: string, action: "submit" | "review" | "approve" | "return", note?: string) =>
    request<ReportingPeriod>(`/api/v1/periods/${periodId}/${action}`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),

  // ---- reports and dashboards ----
  reportOverview: (year: number, month?: number | null) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    return request<NationalOverview>(`/api/v1/reports/overview?${qs.toString()}`);
  },
  reportHospital: (hospitalId: string, year: number, month?: number | null) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    return request<HospitalReport>(`/api/v1/reports/hospital/${hospitalId}?${qs.toString()}`);
  },
  reportTrend: (indicatorId: string, hospitalId: string, months = 12) => {
    const qs = new URLSearchParams({ indicator_id: indicatorId, hospital_id: hospitalId, months: String(months) });
    return request<TrendResponse>(`/api/v1/reports/trend?${qs.toString()}`);
  },
  reportCompare: (year: number, month?: number | null) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    return request<CompareResponse>(`/api/v1/reports/compare?${qs.toString()}`);
  },
  reportLate: (year: number, month?: number | null) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    return request<LateResponse>(`/api/v1/reports/late?${qs.toString()}`);
  },

  // ---- quality and patient safety (v0.7) ----
  qualitySummary: (hospitalId?: string | null) =>
    request<QualitySummary>(
      `/api/v1/quality/summary${hospitalId ? `?hospital_id=${hospitalId}` : ""}`,
    ),
  incidents: (hospitalId?: string | null, status?: string | null) => {
    const qs = new URLSearchParams();
    if (hospitalId) qs.set("hospital_id", hospitalId);
    if (status) qs.set("status", status);
    return request<Incident[]>(`/api/v1/quality/incidents${qs.toString() ? `?${qs}` : ""}`);
  },
  createIncident: (body: Record<string, unknown>) =>
    request<Incident>("/api/v1/quality/incidents", { method: "POST", body: JSON.stringify(body) }),
  updateIncident: (id: string, body: Record<string, unknown>) =>
    request<Incident>(`/api/v1/quality/incidents/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  incidentStatus: (id: string, status: string, note?: string) =>
    request<Incident>(`/api/v1/quality/incidents/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status, note: note ?? null }),
    }),
  rca: (incidentId: string) =>
    request<RcaDetail>(`/api/v1/quality/incidents/${incidentId}/rca`),
  createRca: (incidentId: string, body: Record<string, unknown>) =>
    request<Rca>(`/api/v1/quality/incidents/${incidentId}/rca`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateRca: (rcaId: string, body: Record<string, unknown>) =>
    request<Rca>(`/api/v1/quality/rca/${rcaId}`, { method: "PATCH", body: JSON.stringify(body) }),
  addRcaCause: (rcaId: string, body: Record<string, unknown>) =>
    request<RcaCause>(`/api/v1/quality/rca/${rcaId}/causes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  capa: (hospitalId?: string | null, overdueOnly = false) => {
    const qs = new URLSearchParams();
    if (hospitalId) qs.set("hospital_id", hospitalId);
    if (overdueOnly) qs.set("overdue_only", "true");
    return request<Capa[]>(`/api/v1/quality/capa${qs.toString() ? `?${qs}` : ""}`);
  },
  createCapa: (body: Record<string, unknown>) =>
    request<Capa>("/api/v1/quality/capa", { method: "POST", body: JSON.stringify(body) }),
  updateCapa: (id: string, body: Record<string, unknown>) =>
    request<Capa>(`/api/v1/quality/capa/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  risks: (hospitalId?: string | null) =>
    request<Risk[]>(`/api/v1/quality/risks${hospitalId ? `?hospital_id=${hospitalId}` : ""}`),
  createRisk: (body: Record<string, unknown>) =>
    request<Risk>("/api/v1/quality/risks", { method: "POST", body: JSON.stringify(body) }),
  updateRisk: (id: string, body: Record<string, unknown>) =>
    request<Risk>(`/api/v1/quality/risks/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  qualityAudits: (hospitalId?: string | null) =>
    request<QualityAudit[]>(`/api/v1/quality/audits${hospitalId ? `?hospital_id=${hospitalId}` : ""}`),
  createQualityAudit: (body: Record<string, unknown>) =>
    request<QualityAudit>("/api/v1/quality/audits", { method: "POST", body: JSON.stringify(body) }),
  updateQualityAudit: (id: string, body: Record<string, unknown>) =>
    request<QualityAudit>(`/api/v1/quality/audits/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  qualityPlans: (hospitalId?: string | null) =>
    request<ImprovementPlan[]>(`/api/v1/quality/plans${hospitalId ? `?hospital_id=${hospitalId}` : ""}`),
  qualityPlan: (id: string) => request<ImprovementPlanDetail>(`/api/v1/quality/plans/${id}`),
  createQualityPlan: (body: Record<string, unknown>) =>
    request<ImprovementPlan>("/api/v1/quality/plans", { method: "POST", body: JSON.stringify(body) }),
  updateQualityPlan: (id: string, body: Record<string, unknown>) =>
    request<ImprovementPlan>(`/api/v1/quality/plans/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  addPlanAction: (planId: string, body: Record<string, unknown>) =>
    request<ImprovementAction>(`/api/v1/quality/plans/${planId}/actions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  qualityDocuments: (hospitalId?: string | null) =>
    request<QualityDocument[]>(
      `/api/v1/quality/documents${hospitalId ? `?hospital_id=${hospitalId}` : ""}`,
    ),
  createQualityDocument: (body: Record<string, unknown>) =>
    request<QualityDocument>("/api/v1/quality/documents", { method: "POST", body: JSON.stringify(body) }),
  updateQualityDocument: (id: string, body: Record<string, unknown>) =>
    request<QualityDocument>(`/api/v1/quality/documents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  qualityMeetings: (hospitalId?: string | null) =>
    request<QualityMeeting[]>(
      `/api/v1/quality/meetings${hospitalId ? `?hospital_id=${hospitalId}` : ""}`,
    ),
  qualityMeeting: (id: string) => request<MeetingDetail>(`/api/v1/quality/meetings/${id}`),
  createQualityMeeting: (body: Record<string, unknown>) =>
    request<QualityMeeting>("/api/v1/quality/meetings", { method: "POST", body: JSON.stringify(body) }),
  updateQualityMeeting: (id: string, body: Record<string, unknown>) =>
    request<QualityMeeting>(`/api/v1/quality/meetings/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  addMeetingDecision: (meetingId: string, body: Record<string, unknown>) =>
    request<MeetingDecision>(`/api/v1/quality/meetings/${meetingId}/decisions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // ---- assistant (v0.8) ----
  assistantStatus: () => request<AssistantStatus>("/api/v1/assistant/status"),
  assistantNational: (year: number, month?: number | null) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    return request<NationalInsight>(`/api/v1/assistant/national?${qs.toString()}`);
  },
  assistantHospital: (hospitalId: string, year: number, month?: number | null) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    return request<HospitalInsight>(`/api/v1/assistant/hospital/${hospitalId}?${qs.toString()}`);
  },
  assistantDraftReport: (hospitalId: string, year: number, month?: number | null) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    return request<DraftReport>(`/api/v1/assistant/hospital/${hospitalId}/draft-report?${qs.toString()}`);
  },
  // ---- alerts (v0.9) ----
  alerts: (year: number, month?: number | null, hospitalId?: string | null, includeAcked = true) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    if (hospitalId) qs.set("hospital_id", hospitalId);
    if (!includeAcked) qs.set("include_acked", "false");
    return request<AlertList>(`/api/v1/alerts?${qs.toString()}`);
  },
  acknowledgeAlert: (
    key: string,
    year: number,
    month: number | null | undefined,
    hospitalId: string | null | undefined,
    note?: string,
  ) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    if (hospitalId) qs.set("hospital_id", hospitalId);
    return request<Alert>(`/api/v1/alerts/${key}/ack?${qs.toString()}`, {
      method: "POST",
      body: JSON.stringify({ note_ar: note ?? null }),
    });
  },
  reopenAlert: (
    key: string,
    year: number,
    month: number | null | undefined,
    hospitalId: string | null | undefined,
  ) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    if (hospitalId) qs.set("hospital_id", hospitalId);
    return request<Alert>(`/api/v1/alerts/${key}/reopen?${qs.toString()}`, { method: "POST" });
  },
  // ---- alert rules (v0.10) ----
  alertRules: (hospitalId?: string | null) => {
    const qs = new URLSearchParams();
    if (hospitalId) qs.set("hospital_id", hospitalId);
    const suffix = qs.toString();
    return request<AlertRuleCatalogue>(`/api/v1/alert-rules${suffix ? `?${suffix}` : ""}`);
  },
  updateAlertRule: (
    kind: string,
    body: { params: Record<string, number>; is_enabled: boolean; note_ar?: string | null },
    hospitalId?: string | null,
  ) => {
    const qs = new URLSearchParams();
    if (hospitalId) qs.set("hospital_id", hospitalId);
    const suffix = qs.toString();
    return request<AlertRule>(`/api/v1/alert-rules/${kind}${suffix ? `?${suffix}` : ""}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  resetAlertRule: (kind: string, hospitalId?: string | null) => {
    const qs = new URLSearchParams();
    if (hospitalId) qs.set("hospital_id", hospitalId);
    const suffix = qs.toString();
    return request<AlertRule>(`/api/v1/alert-rules/${kind}/reset${suffix ? `?${suffix}` : ""}`, {
      method: "POST",
    });
  },
  downloadReport: (format: "xlsx" | "pdf", year: number, month?: number | null, hospitalId?: string) => {
    const qs = new URLSearchParams({ year: String(year) });
    if (month) qs.set("month", String(month));
    if (hospitalId) qs.set("hospital_id", hospitalId);
    return downloadFile(
      `/api/v1/reports/export.${format}?${qs.toString()}`,
      `report-${year}-${month ?? "all"}.${format}`,
    );
  },
};

async function downloadFile(path: string, filename: string): Promise<void> {
  const access = getAccess();
  const res = await fetch(`${BASE}${path}`, {
    headers: access ? { Authorization: `Bearer ${access}` } : undefined,
  });
  if (!res.ok) {
    let message = "تعذّر إنشاء الملف.";
    try {
      const body = await res.json();
      message = body.detail?.message_ar ?? body.error?.message_ar ?? message;
    } catch {
      /* keep default */
    }
    throw new ApiError(res.status, "download_failed", message);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
