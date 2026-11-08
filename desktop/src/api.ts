// Minimal API client for the national quality backend (v0.1).
import type {
  Alert,
  AlertList,
  AlertRule,
  AlertRuleCatalogue,
  AssignedIndicator,
  AssistantStatus,
  AuditFacets,
  AuditLogPage,
  CapaAction,
  CapaCreate,
  CompareResponse,
  Department,
  DraftReport,
  Hospital,
  HospitalInsight,
  HospitalReport,
  ImprovementAction,
  ImprovementPlan,
  Incident,
  IncidentCreate,
  IncidentStatus,
  Indicator,
  LateResponse,
  Me,
  NationalInsight,
  NationalOverview,
  Organization,
  PeriodDetail,
  QualityAudit,
  QualitySummary,
  ReportingPeriod,
  Risk,
  RiskCreate,
  SyncBootstrapResponse,
  SyncPullResponse,
  SyncPushResponse,
  SyncStatusResponse,
  TokenResponse,
  TrendResponse,
  UserOut,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const ACCESS_KEY = "yhq.access";
const REFRESH_KEY = "yhq.refresh";

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

export function getRefresh(): string | null {
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

async function request<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  const access = getAccess();
  if (access) headers.Authorization = `Bearer ${access}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401 && retry && getRefresh()) {
    const ok = await tryRefresh();
    if (ok) return request<T>(path, options, false);
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
  organizations: () => request<Organization[]>("/api/v1/organizations"),
  createOrganization: (body: { name_ar: string; level: string; code?: string }) =>
    request<Organization>("/api/v1/organizations", { method: "POST", body: JSON.stringify(body) }),
  hospitals: () => request<Hospital[]>("/api/v1/hospitals"),
  createHospital: (body: { name_ar: string; code: string; governorate_id?: string }) =>
    request<Hospital>("/api/v1/hospitals", { method: "POST", body: JSON.stringify(body) }),
  departments: (hospitalId: string) =>
    request<Department[]>(`/api/v1/hospitals/${hospitalId}/departments`),
  createDepartment: (hospitalId: string, body: { name_ar: string; code?: string }) =>
    request<Department>(`/api/v1/hospitals/${hospitalId}/departments`, {
      method: "POST",
      body: JSON.stringify({ ...body, hospital_id: hospitalId }),
    }),
  users: () => request<UserOut[]>("/api/v1/users"),
  createUser: (body: { username: string; display_name: string; password: string }) =>
    request<UserOut>("/api/v1/users", { method: "POST", body: JSON.stringify(body) }),
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

  // ---- v0.4: indicators and reporting ----
  indicators: (search?: string) =>
    request<Indicator[]>(`/api/v1/indicators${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  createIndicator: (body: Partial<Indicator> & { code: string; name_ar: string }) =>
    request<Indicator>("/api/v1/indicators", { method: "POST", body: JSON.stringify(body) }),
  assignedIndicators: (hospitalId: string, departmentId?: string) =>
    request<AssignedIndicator[]>(
      `/api/v1/hospitals/${hospitalId}/indicators${
        departmentId ? `?department_id=${departmentId}` : ""
      }`,
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
    request<void>(`/api/v1/hospitals/${hospitalId}/indicators/${assignmentId}`, {
      method: "DELETE",
    }),
  periods: (hospitalId?: string, year?: number) => {
    const qs = new URLSearchParams();
    if (hospitalId) qs.set("hospital_id", hospitalId);
    if (year) qs.set("year", String(year));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<ReportingPeriod[]>(`/api/v1/periods${suffix}`);
  },
  createPeriod: (body: {
    hospital_id: string;
    period_type: string;
    year: number;
    month?: number | null;
    quarter?: number | null;
  }) => request<ReportingPeriod>("/api/v1/periods", { method: "POST", body: JSON.stringify(body) }),
  periodDetail: (periodId: string) => request<PeriodDetail>(`/api/v1/periods/${periodId}`),
  upsertValue: (
    periodId: string,
    body: {
      indicator_id: string;
      department_id?: string | null;
      numerator?: number | null;
      denominator?: number | null;
      entered_value?: number | null;
      note?: string | null;
    },
  ) =>
    request<PeriodDetail["values"][number]>(`/api/v1/periods/${periodId}/values`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  periodAction: (periodId: string, action: "submit" | "review" | "approve" | "return", note?: string) =>
    request<ReportingPeriod>(`/api/v1/periods/${periodId}/${action}`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),

  // ---- v0.5: reports, dashboards and exports ----
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
  downloadReport: (format: "xlsx" | "pdf", year: number, month?: number | null, hospitalId?: string) =>
    downloadFile(
      `/api/v1/reports/export.${format}?${reportQuery(year, month, hospitalId).toString()}`,
      `report-${year}-${month ?? "all"}.${format}`,
    ),

  // ---- v0.6: sync ----
  syncPush: (body: {
    node_id: string;
    hospital_id?: string | null;
    batch_id: string;
    operations: {
      op_id: string;
      entity_type: string;
      entity_id: string;
      op: string;
      base_rev: number;
      payload: Record<string, unknown>;
    }[];
  }) => request<SyncPushResponse>("/api/v1/sync/push", { method: "POST", body: JSON.stringify(body) }),
  syncPull: (since: number, nodeId?: string, limit = 500) => {
    const qs = new URLSearchParams({ since: String(since), limit: String(limit) });
    if (nodeId) qs.set("node_id", nodeId);
    return request<SyncPullResponse>(`/api/v1/sync/pull?${qs.toString()}`);
  },
  syncBootstrap: (nodeId: string, hospitalId?: string) => {
    const qs = new URLSearchParams({ node_id: nodeId });
    if (hospitalId) qs.set("hospital_id", hospitalId);
    return request<SyncBootstrapResponse>(`/api/v1/sync/bootstrap?${qs.toString()}`, { method: "POST" });
  },
  syncStatus: (nodeId?: string) => {
    const qs = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
    return request<SyncStatusResponse>(`/api/v1/sync/status${qs}`);
  },

  // ---- v0.7: quality and patient safety ----
  qualitySummary: (hospitalId?: string) => {
    const qs = hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : "";
    return request<QualitySummary>(`/api/v1/quality/summary${qs}`);
  },
  incidents: (hospitalId?: string, status?: string) => {
    const qs = new URLSearchParams();
    if (hospitalId) qs.set("hospital_id", hospitalId);
    if (status) qs.set("status", status);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<Incident[]>(`/api/v1/quality/incidents${suffix}`);
  },
  createIncident: (body: IncidentCreate) =>
    request<Incident>("/api/v1/quality/incidents", { method: "POST", body: JSON.stringify(body) }),
  updateIncident: (id: string, body: Partial<IncidentCreate>) =>
    request<Incident>(`/api/v1/quality/incidents/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  changeIncidentStatus: (id: string, status: IncidentStatus, note?: string) =>
    request<Incident>(`/api/v1/quality/incidents/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status, note: note ?? null }),
    }),
  capa: (hospitalId?: string) => {
    const qs = hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : "";
    return request<CapaAction[]>(`/api/v1/quality/capa${qs}`);
  },
  createCapa: (body: CapaCreate) =>
    request<CapaAction>("/api/v1/quality/capa", { method: "POST", body: JSON.stringify(body) }),
  risks: (hospitalId?: string) => {
    const qs = hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : "";
    return request<Risk[]>(`/api/v1/quality/risks${qs}`);
  },
  createRisk: (body: RiskCreate) =>
    request<Risk>("/api/v1/quality/risks", { method: "POST", body: JSON.stringify(body) }),
  audits: (hospitalId?: string) => {
    const qs = hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : "";
    return request<QualityAudit[]>(`/api/v1/quality/audits${qs}`);
  },
  plans: (hospitalId?: string) => {
    const qs = hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : "";
    return request<ImprovementPlan[]>(`/api/v1/quality/plans${qs}`);
  },
  planActions: (planId: string) =>
    request<{ plan: ImprovementPlan; actions: ImprovementAction[] }>(
      `/api/v1/quality/plans/${encodeURIComponent(planId)}`,
    ),

  // ---- v0.8: smart assistant ----
  assistantStatus: () => request<AssistantStatus>("/api/v1/assistant/status"),
  assistantNational: (year: number, month?: number | null) => {
    const qs = reportQuery(year, month);
    return request<NationalInsight>(`/api/v1/assistant/national?${qs.toString()}`);
  },
  assistantHospital: (hospitalId: string, year: number, month?: number | null) => {
    const qs = reportQuery(year, month);
    return request<HospitalInsight>(`/api/v1/assistant/hospital/${hospitalId}?${qs.toString()}`);
  },
  assistantDraftReport: (hospitalId: string, year: number, month?: number | null) => {
    const qs = reportQuery(year, month);
    return request<DraftReport>(`/api/v1/assistant/hospital/${hospitalId}/draft-report?${qs.toString()}`);
  },

  // ---- v0.9: alert centre ----
  alerts: (year: number, month?: number | null, hospitalId?: string | null, includeAcked = true) => {
    const qs = reportQuery(year, month, hospitalId ?? undefined);
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
    const qs = reportQuery(year, month, hospitalId ?? undefined);
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
    const qs = reportQuery(year, month, hospitalId ?? undefined);
    return request<Alert>(`/api/v1/alerts/${key}/reopen?${qs.toString()}`, { method: "POST" });
  },

  // ---- v0.10: configurable alert rules ----
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
};

function reportQuery(year: number, month?: number | null, hospitalId?: string): URLSearchParams {
  const qs = new URLSearchParams({ year: String(year) });
  if (month) qs.set("month", String(month));
  if (hospitalId) qs.set("hospital_id", hospitalId);
  return qs;
}

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
