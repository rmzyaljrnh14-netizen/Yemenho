// Quality & patient safety page for the desktop app (v0.7).
//
// Reporting an incident is the one quality task a hospital must be able to do
// with no internet, so this page is offline-first: on the desktop it writes to
// the local SQLite store and queues an outbox op (the sync engine sends it when
// the connection returns); in a browser it talks to the API directly.

import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { hasPermission, useAuth } from "../auth";
import { desktop, isDesktop } from "../desktop";
import type {
  CapaAction,
  CapaKind,
  CapaPriority,
  Department,
  ImprovementAction,
  ImprovementPlan,
  Incident,
  IncidentCreate,
  IncidentSeverity,
  IncidentStatus,
  IncidentType,
  PatientHarm,
  QualityAudit,
  QualitySummary,
  Risk,
  RiskCategory,
} from "../types";

const DESK = isDesktop();

const INCIDENT_TYPE_AR: Record<string, string> = {
  medication: "دواء",
  fall: "سقوط",
  pressure_ulcer: "قرحة ضغط",
  infection: "عدوى",
  surgical: "جراحي",
  diagnostic: "تشخيصي",
  transfusion: "نقل دم",
  equipment: "أجهزة",
  behaviour: "سلوكي",
  other: "أخرى",
};

const SEVERITY_AR: Record<string, string> = {
  near_miss: "شبه حادث",
  minor: "خفيف",
  moderate: "متوسط",
  major: "جسيم",
  catastrophic: "كارثي",
};

const HARM_AR: Record<string, string> = {
  none: "لا ضرر",
  mild: "ضرر بسيط",
  moderate: "ضرر متوسط",
  severe: "ضرر شديد",
  death: "وفاة",
};

const STATUS_AR: Record<string, string> = {
  reported: "مُبلَّغ",
  under_review: "قيد المراجعة",
  rca: "تحليل الأسباب",
  capa: "إجراءات تصحيحية",
  closed: "مغلق",
  rejected: "مرفوض",
};

const SEVERITY_CLASS: Record<string, string> = {
  near_miss: "badge",
  minor: "badge",
  moderate: "badge warn",
  major: "badge off",
  catastrophic: "badge off",
};

const CAPA_KIND_AR: Record<string, string> = {
  corrective: "تصحيحي",
  preventive: "وقائي",
};

const CAPA_PRIORITY_AR: Record<string, string> = {
  low: "منخفضة",
  medium: "متوسطة",
  high: "عالية",
  critical: "حرجة",
};

const CAPA_STATUS_AR: Record<string, string> = {
  open: "مفتوح",
  in_progress: "قيد التنفيذ",
  done: "منجز",
  verified: "متحقَّق منه",
  cancelled: "ملغى",
};

const PRIORITY_CLASS: Record<string, string> = {
  low: "badge",
  medium: "badge",
  high: "badge warn",
  critical: "badge off",
};

const RISK_CATEGORY_AR: Record<string, string> = {
  clinical: "سريري",
  medication: "دوائي",
  infection: "عدوى",
  environment: "بيئي",
  equipment: "أجهزة",
  staffing: "كوادر",
  information: "معلومات",
  security: "أمني",
  other: "أخرى",
};

const RISK_STATUS_AR: Record<string, string> = {
  open: "مفتوح",
  mitigated: "مُخفَّف",
  accepted: "مقبول",
  closed: "مغلق",
};

const AUDIT_STATUS_AR: Record<string, string> = {
  planned: "مُخطَّط",
  in_progress: "قيد التنفيذ",
  completed: "مكتمل",
  closed: "مغلق",
};

const PLAN_STATUS_AR: Record<string, string> = {
  draft: "مسودة",
  active: "نشطة",
  completed: "مكتملة",
  cancelled: "ملغاة",
};

const PLAN_ACTION_STATUS_AR: Record<string, string> = {
  open: "مفتوحة",
  in_progress: "قيد التنفيذ",
  done: "منجزة",
  cancelled: "ملغاة",
};

function riskLevel(score: number | null): { label: string; cls: string } {
  if (score === null) return { label: "—", cls: "badge" };
  if (score >= 15) return { label: `عالٍ (${score})`, cls: "badge off" };
  if (score >= 8) return { label: `متوسط (${score})`, cls: "badge warn" };
  return { label: `منخفض (${score})`, cls: "badge on" };
}

function newId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `inc-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// A row the local store returns lacks the server's fields (code, timestamps);
// fill them so the list renders the same shape online and offline.
function localIncident(raw: Record<string, unknown>): Incident & { synced?: boolean } {
  return {
    id: String(raw.id),
    hospital_id: String(raw.hospital_id ?? ""),
    department_id: (raw.department_id as string | null) ?? null,
    code: String(raw.code ?? "بانتظار المزامنة"),
    title: String(raw.title ?? ""),
    description: (raw.description as string | null) ?? null,
    incident_type: (raw.incident_type as IncidentType) ?? "other",
    severity: (raw.severity as IncidentSeverity) ?? "moderate",
    patient_harm: (raw.patient_harm as PatientHarm) ?? "none",
    occurred_at: (raw.occurred_at as string | null) ?? null,
    reported_at: String(raw.reported_at ?? raw.updated_at ?? ""),
    is_anonymous: Boolean(raw.is_anonymous),
    status: (raw.status as IncidentStatus) ?? "reported",
    immediate_action: (raw.immediate_action as string | null) ?? null,
    closed_at: null,
    rev: Number(raw.rev ?? 0),
    created_at: "",
    updated_at: "",
    synced: Boolean(raw.synced),
  };
}

const EMPTY_FORM = {
  title: "",
  description: "",
  incident_type: "other" as IncidentType,
  severity: "moderate" as IncidentSeverity,
  patient_harm: "none" as PatientHarm,
  department_id: "",
  occurred_at: "",
  is_anonymous: false,
  immediate_action: "",
};

const EMPTY_CAPA_FORM = {
  kind: "corrective" as CapaKind,
  title: "",
  description_ar: "",
  owner_name_ar: "",
  due_date: "",
  priority: "medium" as CapaPriority,
  department_id: "",
};

const EMPTY_RISK_FORM = {
  title: "",
  description_ar: "",
  category: "clinical" as RiskCategory,
  likelihood: 3,
  impact: 3,
  mitigation_ar: "",
  owner_name_ar: "",
  review_date: "",
  department_id: "",
};

const EMPTY_AUDIT_FORM = {
  title: "",
  standard_ar: "",
  scope_ar: "",
  auditor_name_ar: "",
  audit_date: "",
  department_id: "",
};

const EMPTY_PLAN_FORM = {
  title: "",
  objective_ar: "",
  baseline_ar: "",
  target_ar: "",
  owner_name_ar: "",
  start_date: "",
  due_date: "",
  department_id: "",
};

const EMPTY_PLAN_ACTION_FORM = {
  title: "",
  owner_name_ar: "",
  due_date: "",
  note_ar: "",
};

// A row the local store returns lacks server fields (code, is_overdue); fill them
// so the list renders the same shape online and offline.
function localCapa(raw: Record<string, unknown>): CapaAction {
  return {
    id: String(raw.id),
    hospital_id: String(raw.hospital_id ?? ""),
    department_id: (raw.department_id as string | null) ?? null,
    incident_id: (raw.incident_id as string | null) ?? null,
    rca_id: null,
    audit_id: null,
    kind: (raw.kind as CapaKind) ?? "corrective",
    title: String(raw.title ?? ""),
    description_ar: (raw.description_ar as string | null) ?? null,
    owner_name_ar: (raw.owner_name_ar as string | null) ?? null,
    due_date: (raw.due_date as string | null) ?? null,
    priority: (raw.priority as CapaPriority) ?? "medium",
    status: (raw.status as CapaAction["status"]) ?? "open",
    completion_note_ar: (raw.completion_note_ar as string | null) ?? null,
    is_overdue: false,
    synced: Boolean(raw.synced),
  };
}

function localRisk(raw: Record<string, unknown>): Risk {
  return {
    id: String(raw.id),
    hospital_id: String(raw.hospital_id ?? ""),
    department_id: (raw.department_id as string | null) ?? null,
    code: String(raw.code ?? "بانتظار المزامنة"),
    title: String(raw.title ?? ""),
    description_ar: (raw.description_ar as string | null) ?? null,
    category: (raw.category as RiskCategory) ?? "clinical",
    likelihood: Number(raw.likelihood ?? 3),
    impact: Number(raw.impact ?? 3),
    score: raw.score === null || raw.score === undefined ? null : Number(raw.score),
    mitigation_ar: (raw.mitigation_ar as string | null) ?? null,
    owner_name_ar: (raw.owner_name_ar as string | null) ?? null,
    review_date: (raw.review_date as string | null) ?? null,
    status: (raw.status as Risk["status"]) ?? "open",
    rev: Number(raw.rev ?? 0),
    synced: Boolean(raw.synced),
  };
}

function localAudit(raw: Record<string, unknown>): QualityAudit {
  return {
    id: String(raw.id),
    hospital_id: String(raw.hospital_id ?? ""),
    department_id: (raw.department_id as string | null) ?? null,
    code: String(raw.code ?? "بانتظار المزامنة"),
    title: String(raw.title ?? ""),
    standard_ar: (raw.standard_ar as string | null) ?? null,
    scope_ar: (raw.scope_ar as string | null) ?? null,
    auditor_name_ar: (raw.auditor_name_ar as string | null) ?? null,
    audit_date: (raw.audit_date as string | null) ?? null,
    status: (raw.status as QualityAudit["status"]) ?? "planned",
    score: raw.score === null || raw.score === undefined ? null : Number(raw.score),
    findings_ar: (raw.findings_ar as string | null) ?? null,
    rev: Number(raw.rev ?? 0),
    synced: Boolean(raw.synced),
  };
}

function localPlan(raw: Record<string, unknown>): ImprovementPlan {
  return {
    id: String(raw.id),
    hospital_id: String(raw.hospital_id ?? ""),
    department_id: (raw.department_id as string | null) ?? null,
    code: String(raw.code ?? "بانتظار المزامنة"),
    title: String(raw.title ?? ""),
    objective_ar: (raw.objective_ar as string | null) ?? null,
    baseline_ar: (raw.baseline_ar as string | null) ?? null,
    target_ar: (raw.target_ar as string | null) ?? null,
    indicator_id: (raw.indicator_id as string | null) ?? null,
    owner_name_ar: (raw.owner_name_ar as string | null) ?? null,
    start_date: (raw.start_date as string | null) ?? null,
    due_date: (raw.due_date as string | null) ?? null,
    status: (raw.status as ImprovementPlan["status"]) ?? "draft",
    rev: Number(raw.rev ?? 0),
    synced: Boolean(raw.synced),
  };
}

function localPlanAction(raw: Record<string, unknown>): ImprovementAction {
  return {
    id: String(raw.id),
    plan_id: String(raw.plan_id ?? ""),
    title: String(raw.title ?? ""),
    owner_name_ar: (raw.owner_name_ar as string | null) ?? null,
    due_date: (raw.due_date as string | null) ?? null,
    status: (raw.status as ImprovementAction["status"]) ?? "open",
    note_ar: (raw.note_ar as string | null) ?? null,
    rev: Number(raw.rev ?? 0),
    synced: Boolean(raw.synced),
  };
}

export default function Quality() {
  const { me } = useAuth();
  const canManage = hasPermission(me, "quality.manage");
  const hospitalId = me?.scope_org.hospital_id ?? null;

  const [summary, setSummary] = useState<QualitySummary | null>(null);
  const [rows, setRows] = useState<(Incident & { synced?: boolean })[]>([]);
  const [capaRows, setCapaRows] = useState<CapaAction[]>([]);
  const [riskRows, setRiskRows] = useState<Risk[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [showForm, setShowForm] = useState(false);
  const [capaForm, setCapaForm] = useState({ ...EMPTY_CAPA_FORM });
  const [showCapaForm, setShowCapaForm] = useState(false);
  const [riskForm, setRiskForm] = useState({ ...EMPTY_RISK_FORM });
  const [showRiskForm, setShowRiskForm] = useState(false);
  const [auditRows, setAuditRows] = useState<QualityAudit[]>([]);
  const [auditForm, setAuditForm] = useState({ ...EMPTY_AUDIT_FORM });
  const [showAuditForm, setShowAuditForm] = useState(false);
  const [planRows, setPlanRows] = useState<ImprovementPlan[]>([]);
  const [planForm, setPlanForm] = useState({ ...EMPTY_PLAN_FORM });
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [planActions, setPlanActions] = useState<Record<string, ImprovementAction[]>>({});
  const [openPlanId, setOpenPlanId] = useState<string | null>(null);
  const [actionForm, setActionForm] = useState({ ...EMPTY_PLAN_ACTION_FORM });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    // Incidents: prefer the local store on the desktop so the list is complete
    // and instant, and merge the server's authoritative rows when online.
    let local: (Incident & { synced?: boolean })[] = [];
    if (DESK) {
      const raw = (await desktop.listIncidents(hospitalId)) ?? [];
      local = raw.map(localIncident);
    }
    let server: Incident[] = [];
    try {
      server = await api.incidents(hospitalId ?? undefined);
    } catch {
      // Offline: the local rows are all we have, and that is fine.
    }
    const byId = new Map<string, Incident & { synced?: boolean }>();
    for (const i of local) byId.set(i.id, i);
    for (const i of server) byId.set(i.id, { ...i, synced: true });
    setRows([...byId.values()].sort((a, b) => (a.reported_at < b.reported_at ? 1 : -1)));

    // CAPA actions and the risk register are offline-first too (v0.14): merge the
    // local store's rows with the server's, local rows win until they sync.
    let localCapaRows: CapaAction[] = [];
    let localRiskRows: Risk[] = [];
    if (DESK) {
      localCapaRows = ((await desktop.listCapa(hospitalId)) ?? []).map(localCapa);
      localRiskRows = ((await desktop.listRisks(hospitalId)) ?? []).map(localRisk);
    }
    let serverCapa: CapaAction[] = [];
    let serverRisk: Risk[] = [];
    try {
      serverCapa = await api.capa(hospitalId ?? undefined);
    } catch {
      /* offline */
    }
    try {
      serverRisk = await api.risks(hospitalId ?? undefined);
    } catch {
      /* offline */
    }
    const capaById = new Map<string, CapaAction>();
    for (const c of localCapaRows) capaById.set(c.id, c);
    for (const c of serverCapa) capaById.set(c.id, { ...c, synced: true });
    setCapaRows([...capaById.values()]);

    const riskById = new Map<string, Risk>();
    for (const r of localRiskRows) riskById.set(r.id, r);
    for (const r of serverRisk) riskById.set(r.id, { ...r, synced: true });
    setRiskRows([...riskById.values()].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)));

    // Internal audits and improvement plans join the offline-first set (v0.15).
    let localAuditRows: QualityAudit[] = [];
    let localPlanRows: ImprovementPlan[] = [];
    if (DESK) {
      localAuditRows = ((await desktop.listAudits(hospitalId)) ?? []).map(localAudit);
      localPlanRows = ((await desktop.listPlans(hospitalId)) ?? []).map(localPlan);
    }
    let serverAudits: QualityAudit[] = [];
    let serverPlans: ImprovementPlan[] = [];
    try {
      serverAudits = await api.audits(hospitalId ?? undefined);
    } catch {
      /* offline */
    }
    try {
      serverPlans = await api.plans(hospitalId ?? undefined);
    } catch {
      /* offline */
    }
    const auditById = new Map<string, QualityAudit>();
    for (const a of localAuditRows) auditById.set(a.id, a);
    for (const a of serverAudits) auditById.set(a.id, { ...a, synced: true });
    setAuditRows([...auditById.values()]);

    const planById = new Map<string, ImprovementPlan>();
    for (const p of localPlanRows) planById.set(p.id, p);
    for (const p of serverPlans) planById.set(p.id, { ...p, synced: true });
    setPlanRows([...planById.values()]);

    try {
      setSummary(await api.qualitySummary(hospitalId ?? undefined));
    } catch {
      setSummary(null);
    }

    // Departments: from the local cache offline, from the API online.
    if (DESK) {
      const raw = (await desktop.listDepartments()) ?? [];
      if (raw.length > 0) {
        setDepartments(raw.map((d) => ({
          id: String(d.id),
          hospital_id: String(d.hospital_id ?? ""),
          name_ar: String(d.name_ar ?? ""),
          code: (d.code as string | null) ?? null,
          is_active: Boolean(d.is_active),
        })));
        return;
      }
    }
    if (hospitalId) {
      try {
        setDepartments(await api.departments(hospitalId));
      } catch {
        /* keep whatever we have */
      }
    }
  }, [hospitalId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit() {
    if (form.title.trim().length < 3) {
      setError("أدخل عنواناً واضحاً للحادث (٣ أحرف على الأقل).");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    const payload: IncidentCreate = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      incident_type: form.incident_type,
      severity: form.severity,
      patient_harm: form.patient_harm,
      department_id: form.department_id || null,
      occurred_at: form.occurred_at || null,
      is_anonymous: form.is_anonymous,
      immediate_action: form.immediate_action.trim() || null,
    };
    try {
      if (DESK && hospitalId) {
        // Write locally first, queue for sync: this must work with no internet.
        await desktop.saveIncident({
          incident_id: newId(),
          hospital_id: hospitalId,
          department_id: payload.department_id ?? null,
          title: payload.title,
          description: payload.description ?? null,
          incident_type: payload.incident_type,
          severity: payload.severity,
          patient_harm: payload.patient_harm,
          occurred_at: payload.occurred_at ?? null,
          is_anonymous: payload.is_anonymous ?? false,
          immediate_action: payload.immediate_action ?? null,
        });
        setNotice("حُفظ الحادث محلياً وسيُرسَل تلقائياً عند توفر الاتصال.");
      } else {
        await api.createIncident(payload);
        setNotice("سُجّل الحادث على الخادم.");
      }
      setForm({ ...EMPTY_FORM });
      setShowForm(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر حفظ الحادث.");
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(row: Incident, status: IncidentStatus) {
    setBusy(true);
    setError(null);
    try {
      await api.changeIncidentStatus(row.id, status);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تغيير حالة الحادث.");
    } finally {
      setBusy(false);
    }
  }

  async function submitCapa() {
    if (capaForm.title.trim().length < 3) {
      setError("أدخل عنواناً واضحاً للإجراء (٣ أحرف على الأقل).");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (DESK && hospitalId) {
        await desktop.saveCapa({
          capa_id: newId(),
          hospital_id: hospitalId,
          department_id: capaForm.department_id || null,
          kind: capaForm.kind,
          title: capaForm.title.trim(),
          description_ar: capaForm.description_ar.trim() || null,
          owner_name_ar: capaForm.owner_name_ar.trim() || null,
          due_date: capaForm.due_date || null,
          priority: capaForm.priority,
        });
        setNotice("حُفظ الإجراء محلياً وسيُرسَل تلقائياً عند توفر الاتصال.");
      } else {
        await api.createCapa({
          department_id: capaForm.department_id || null,
          kind: capaForm.kind,
          title: capaForm.title.trim(),
          description_ar: capaForm.description_ar.trim() || null,
          owner_name_ar: capaForm.owner_name_ar.trim() || null,
          due_date: capaForm.due_date || null,
          priority: capaForm.priority,
        });
        setNotice("سُجّل الإجراء على الخادم.");
      }
      setCapaForm({ ...EMPTY_CAPA_FORM });
      setShowCapaForm(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر حفظ الإجراء التصحيحي.");
    } finally {
      setBusy(false);
    }
  }

  async function submitRisk() {
    if (riskForm.title.trim().length < 3) {
      setError("أدخل عنواناً واضحاً للخطر (٣ أحرف على الأقل).");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (DESK && hospitalId) {
        await desktop.saveRisk({
          risk_id: newId(),
          hospital_id: hospitalId,
          department_id: riskForm.department_id || null,
          title: riskForm.title.trim(),
          description_ar: riskForm.description_ar.trim() || null,
          category: riskForm.category,
          likelihood: riskForm.likelihood,
          impact: riskForm.impact,
          mitigation_ar: riskForm.mitigation_ar.trim() || null,
          owner_name_ar: riskForm.owner_name_ar.trim() || null,
          review_date: riskForm.review_date || null,
        });
        setNotice("حُفظ الخطر محلياً وسيُرسَل تلقائياً عند توفر الاتصال.");
      } else {
        await api.createRisk({
          department_id: riskForm.department_id || null,
          title: riskForm.title.trim(),
          description_ar: riskForm.description_ar.trim() || null,
          category: riskForm.category,
          likelihood: riskForm.likelihood,
          impact: riskForm.impact,
          mitigation_ar: riskForm.mitigation_ar.trim() || null,
          owner_name_ar: riskForm.owner_name_ar.trim() || null,
          review_date: riskForm.review_date || null,
        });
        setNotice("سُجّل الخطر على الخادم.");
      }
      setRiskForm({ ...EMPTY_RISK_FORM });
      setShowRiskForm(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر حفظ الخطر.");
    } finally {
      setBusy(false);
    }
  }

  async function submitAudit() {
    if (auditForm.title.trim().length < 3) {
      setError("أدخل عنواناً واضحاً للتدقيق (٣ أحرف على الأقل).");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (DESK && hospitalId) {
        await desktop.saveAudit({
          audit_id: newId(),
          hospital_id: hospitalId,
          department_id: auditForm.department_id || null,
          title: auditForm.title.trim(),
          standard_ar: auditForm.standard_ar.trim() || null,
          scope_ar: auditForm.scope_ar.trim() || null,
          auditor_name_ar: auditForm.auditor_name_ar.trim() || null,
          audit_date: auditForm.audit_date || null,
        });
        setNotice("حُفظ التدقيق محلياً وسيُرسَل تلقائياً عند توفر الاتصال.");
      } else {
        setError("إنشاء التدقيق متاح من تطبيق سطح المكتب (يعمل دون اتصال).");
        return;
      }
      setAuditForm({ ...EMPTY_AUDIT_FORM });
      setShowAuditForm(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر حفظ التدقيق.");
    } finally {
      setBusy(false);
    }
  }

  async function submitPlan() {
    if (planForm.title.trim().length < 3) {
      setError("أدخل عنواناً واضحاً لخطة التحسين (٣ أحرف على الأقل).");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (DESK && hospitalId) {
        await desktop.savePlan({
          plan_id: newId(),
          hospital_id: hospitalId,
          department_id: planForm.department_id || null,
          title: planForm.title.trim(),
          objective_ar: planForm.objective_ar.trim() || null,
          baseline_ar: planForm.baseline_ar.trim() || null,
          target_ar: planForm.target_ar.trim() || null,
          owner_name_ar: planForm.owner_name_ar.trim() || null,
          start_date: planForm.start_date || null,
          due_date: planForm.due_date || null,
        });
        setNotice("حُفظت خطة التحسين محلياً وستُرسَل تلقائياً عند توفر الاتصال.");
      } else {
        setError("إنشاء خطة التحسين متاح من تطبيق سطح المكتب (يعمل دون اتصال).");
        return;
      }
      setPlanForm({ ...EMPTY_PLAN_FORM });
      setShowPlanForm(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر حفظ خطة التحسين.");
    } finally {
      setBusy(false);
    }
  }

  async function togglePlan(plan: ImprovementPlan) {
    if (openPlanId === plan.id) {
      setOpenPlanId(null);
      return;
    }
    setOpenPlanId(plan.id);
    setActionForm({ ...EMPTY_PLAN_ACTION_FORM });
    // Load the steps: local store first (offline), then the server.
    let local: ImprovementAction[] = [];
    if (DESK) {
      local = ((await desktop.listPlanActions(plan.id)) ?? []).map(localPlanAction);
    }
    let server: ImprovementAction[] = [];
    try {
      server = (await api.planActions(plan.id)).actions;
    } catch {
      /* offline */
    }
    const byId = new Map<string, ImprovementAction>();
    for (const a of local) byId.set(a.id, a);
    for (const a of server) byId.set(a.id, { ...a, synced: true });
    setPlanActions((prev) => ({ ...prev, [plan.id]: [...byId.values()] }));
  }

  async function submitPlanAction(planId: string) {
    if (actionForm.title.trim().length < 3) {
      setError("أدخل عنواناً واضحاً للخطوة (٣ أحرف على الأقل).");
      return;
    }
    if (!(DESK && hospitalId)) {
      setError("إضافة خطوات الخطة متاحة من تطبيق سطح المكتب (يعمل دون اتصال).");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await desktop.savePlanAction({
        action_id: newId(),
        plan_id: planId,
        title: actionForm.title.trim(),
        owner_name_ar: actionForm.owner_name_ar.trim() || null,
        due_date: actionForm.due_date || null,
        note_ar: actionForm.note_ar.trim() || null,
      });
      setNotice("حُفظت الخطوة محلياً وستُرسَل تلقائياً عند توفر الاتصال.");
      setActionForm({ ...EMPTY_PLAN_ACTION_FORM });
      const rows = ((await desktop.listPlanActions(planId)) ?? []).map(localPlanAction);
      setPlanActions((prev) => ({ ...prev, [planId]: rows }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر حفظ الخطوة.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="topbar" style={{ marginBottom: 12 }}>
        <h2>الجودة وسلامة المرضى</h2>
        {canManage && (
          <button className="badge on" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "إلغاء" : "الإبلاغ عن حادث جديد"}
          </button>
        )}
      </div>

      {!canManage && (
        <div className="card" style={{ background: "#fff7ed", borderColor: "#fdba74" }}>
          وضع القراءة فقط: حسابك لا يملك صلاحية «إدارة الجودة»، فيعرض البيانات دون تعديل.
        </div>
      )}
      {error && <div className="error-box">{error}</div>}
      {notice && <div className="notice-box">{notice}</div>}

      {summary && (
        <div className="stat-grid">
          <div className="stat"><div>إجمالي الحوادث</div><div className="stat-value">{summary.incidents_total}</div></div>
          <div className="stat"><div>حوادث مفتوحة</div><div className="stat-value">{summary.incidents_open}</div></div>
          <div className="stat"><div>مخاطر عالية</div><div className="stat-value">{summary.risks_high}</div></div>
          <div className="stat"><div>إجراءات متأخرة</div><div className="stat-value">{summary.capa_overdue}</div></div>
          <div className="stat"><div>تدقيقات مكتملة</div><div className="stat-value">{summary.audits_completed}</div></div>
          <div className="stat"><div>خطط تحسين نشطة</div><div className="stat-value">{summary.plans_active}</div></div>
        </div>
      )}

      {showForm && canManage && (
        <div className="card">
          <h3>الإبلاغ عن حادث / خطأ طبي</h3>
          <div className="row">
            <div className="field">
              <label>عنوان الحادث</label>
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="مثال: سقوط مريض أثناء النقل"
              />
            </div>
            <div className="field">
              <label>القسم</label>
              <select
                value={form.department_id}
                onChange={(e) => setForm({ ...form, department_id: e.target.value })}
              >
                <option value="">— بدون قسم محدد —</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>{d.name_ar}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>نوع الحادث</label>
              <select
                value={form.incident_type}
                onChange={(e) => setForm({ ...form, incident_type: e.target.value as IncidentType })}
              >
                {Object.entries(INCIDENT_TYPE_AR).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>درجة الخطورة</label>
              <select
                value={form.severity}
                onChange={(e) => setForm({ ...form, severity: e.target.value as IncidentSeverity })}
              >
                {Object.entries(SEVERITY_AR).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>الضرر الواقع على المريض</label>
              <select
                value={form.patient_harm}
                onChange={(e) => setForm({ ...form, patient_harm: e.target.value as PatientHarm })}
              >
                {Object.entries(HARM_AR).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>تاريخ ووقت الحادث</label>
              <input
                type="datetime-local"
                value={form.occurred_at}
                onChange={(e) => setForm({ ...form, occurred_at: e.target.value })}
              />
            </div>
            <div className="field">
              <label>الإجراء الفوري المتخذ</label>
              <input
                value={form.immediate_action}
                onChange={(e) => setForm({ ...form, immediate_action: e.target.value })}
              />
            </div>
          </div>
          <div className="field">
            <label>وصف الحادث</label>
            <textarea
              rows={3}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <label className="hint">
            <input
              type="checkbox"
              checked={form.is_anonymous}
              onChange={(e) => setForm({ ...form, is_anonymous: e.target.checked })}
            />{" "}
            إبلاغ مجهول الهوية
          </label>
          <div className="row">
            <button className="badge on" disabled={busy} onClick={() => void submit()}>
              {busy ? "جارٍ الحفظ..." : "حفظ الحادث"}
            </button>
          </div>
        </div>
      )}

      <div className="card">
        <h3>سجل الحوادث</h3>
        {rows.length === 0 ? (
          <div className="empty">لا توجد حوادث مسجّلة بعد.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>الرمز</th>
                <th>العنوان</th>
                <th>النوع</th>
                <th>الخطورة</th>
                <th>الحالة</th>
                <th>المزامنة</th>
                {canManage && <th>إجراء</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.code}</td>
                  <td>{r.title}</td>
                  <td>{INCIDENT_TYPE_AR[r.incident_type] ?? r.incident_type}</td>
                  <td>
                    <span className={SEVERITY_CLASS[r.severity] ?? "badge"}>
                      {SEVERITY_AR[r.severity] ?? r.severity}
                    </span>
                  </td>
                  <td>{STATUS_AR[r.status] ?? r.status}</td>
                  <td>
                    {r.synced === false ? (
                      <span className="badge warn">بانتظار الإرسال</span>
                    ) : (
                      <span className="badge on">مُزامن</span>
                    )}
                  </td>
                  {canManage && (
                    <td>
                      {r.status !== "closed" && (
                        <select
                          value=""
                          disabled={busy || r.synced === false}
                          onChange={(e) => void changeStatus(r, e.target.value as IncidentStatus)}
                        >
                          <option value="">تغيير الحالة...</option>
                          <option value="under_review">قيد المراجعة</option>
                          <option value="rca">تحليل الأسباب</option>
                          <option value="capa">إجراءات تصحيحية</option>
                          <option value="closed">إغلاق</option>
                          <option value="rejected">رفض</option>
                        </select>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>الإجراءات التصحيحية والوقائية (CAPA)</h3>
        {canManage && (
          <button className="badge on" style={{ marginBottom: 8 }} onClick={() => setShowCapaForm((v) => !v)}>
            {showCapaForm ? "إلغاء" : "إجراء جديد"}
          </button>
        )}
        {showCapaForm && canManage && (
          <div style={{ marginBottom: 12 }}>
            <div className="row">
              <div className="field">
                <label>عنوان الإجراء</label>
                <input
                  value={capaForm.title}
                  onChange={(e) => setCapaForm({ ...capaForm, title: e.target.value })}
                  placeholder="مثال: تدريب الكادر على التحقق من هوية المريض"
                />
              </div>
              <div className="field">
                <label>النوع</label>
                <select
                  value={capaForm.kind}
                  onChange={(e) => setCapaForm({ ...capaForm, kind: e.target.value as CapaKind })}
                >
                  {Object.entries(CAPA_KIND_AR).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>الأولوية</label>
                <select
                  value={capaForm.priority}
                  onChange={(e) => setCapaForm({ ...capaForm, priority: e.target.value as CapaPriority })}
                >
                  {Object.entries(CAPA_PRIORITY_AR).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>القسم</label>
                <select
                  value={capaForm.department_id}
                  onChange={(e) => setCapaForm({ ...capaForm, department_id: e.target.value })}
                >
                  <option value="">— بدون قسم محدد —</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>{d.name_ar}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>المسؤول عن التنفيذ</label>
                <input
                  value={capaForm.owner_name_ar}
                  onChange={(e) => setCapaForm({ ...capaForm, owner_name_ar: e.target.value })}
                />
              </div>
              <div className="field">
                <label>تاريخ الاستحقاق</label>
                <input
                  type="date"
                  value={capaForm.due_date}
                  onChange={(e) => setCapaForm({ ...capaForm, due_date: e.target.value })}
                />
              </div>
            </div>
            <div className="field">
              <label>الوصف</label>
              <textarea
                rows={2}
                value={capaForm.description_ar}
                onChange={(e) => setCapaForm({ ...capaForm, description_ar: e.target.value })}
              />
            </div>
            <button className="badge on" disabled={busy} onClick={() => void submitCapa()}>
              {busy ? "جارٍ الحفظ..." : "حفظ الإجراء"}
            </button>
          </div>
        )}
        {capaRows.length === 0 ? (
          <div className="empty">لا توجد إجراءات مسجّلة بعد.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>العنوان</th>
                <th>النوع</th>
                <th>الأولوية</th>
                <th>الاستحقاق</th>
                <th>الحالة</th>
                <th>المزامنة</th>
              </tr>
            </thead>
            <tbody>
              {capaRows.map((c) => (
                <tr key={c.id}>
                  <td>{c.title}</td>
                  <td>{CAPA_KIND_AR[c.kind] ?? c.kind}</td>
                  <td>
                    <span className={PRIORITY_CLASS[c.priority] ?? "badge"}>
                      {CAPA_PRIORITY_AR[c.priority] ?? c.priority}
                    </span>
                  </td>
                  <td>{c.due_date ?? "—"}</td>
                  <td>{CAPA_STATUS_AR[c.status] ?? c.status}</td>
                  <td>
                    {c.synced === false ? (
                      <span className="badge warn">بانتظار الإرسال</span>
                    ) : (
                      <span className="badge on">مُزامن</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>سجل المخاطر</h3>
        {canManage && (
          <button className="badge on" style={{ marginBottom: 8 }} onClick={() => setShowRiskForm((v) => !v)}>
            {showRiskForm ? "إلغاء" : "خطر جديد"}
          </button>
        )}
        {showRiskForm && canManage && (
          <div style={{ marginBottom: 12 }}>
            <div className="row">
              <div className="field">
                <label>عنوان الخطر</label>
                <input
                  value={riskForm.title}
                  onChange={(e) => setRiskForm({ ...riskForm, title: e.target.value })}
                  placeholder="مثال: خطر العدوى المرتبطة بالقسطرة"
                />
              </div>
              <div className="field">
                <label>التصنيف</label>
                <select
                  value={riskForm.category}
                  onChange={(e) => setRiskForm({ ...riskForm, category: e.target.value as RiskCategory })}
                >
                  {Object.entries(RISK_CATEGORY_AR).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>القسم</label>
                <select
                  value={riskForm.department_id}
                  onChange={(e) => setRiskForm({ ...riskForm, department_id: e.target.value })}
                >
                  <option value="">— بدون قسم محدد —</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>{d.name_ar}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>الاحتمال (١–٥)</label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={riskForm.likelihood}
                  onChange={(e) => setRiskForm({ ...riskForm, likelihood: Number(e.target.value) })}
                />
              </div>
              <div className="field">
                <label>الأثر (١–٥)</label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={riskForm.impact}
                  onChange={(e) => setRiskForm({ ...riskForm, impact: Number(e.target.value) })}
                />
              </div>
              <div className="field">
                <label>تاريخ المراجعة</label>
                <input
                  type="date"
                  value={riskForm.review_date}
                  onChange={(e) => setRiskForm({ ...riskForm, review_date: e.target.value })}
                />
              </div>
              <div className="field">
                <label>المسؤول</label>
                <input
                  value={riskForm.owner_name_ar}
                  onChange={(e) => setRiskForm({ ...riskForm, owner_name_ar: e.target.value })}
                />
              </div>
            </div>
            <div className="field">
              <label>إجراءات التخفيف</label>
              <textarea
                rows={2}
                value={riskForm.mitigation_ar}
                onChange={(e) => setRiskForm({ ...riskForm, mitigation_ar: e.target.value })}
              />
            </div>
            <button className="badge on" disabled={busy} onClick={() => void submitRisk()}>
              {busy ? "جارٍ الحفظ..." : "حفظ الخطر"}
            </button>
          </div>
        )}
        {riskRows.length === 0 ? (
          <div className="empty">لا توجد مخاطر مسجّلة بعد.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>الرمز</th>
                <th>العنوان</th>
                <th>التصنيف</th>
                <th>الاحتمال</th>
                <th>الأثر</th>
                <th>المستوى</th>
                <th>الحالة</th>
                <th>المزامنة</th>
              </tr>
            </thead>
            <tbody>
              {riskRows.map((r) => {
                const lvl = riskLevel(r.score);
                return (
                  <tr key={r.id}>
                    <td>{r.code}</td>
                    <td>{r.title}</td>
                    <td>{RISK_CATEGORY_AR[r.category] ?? r.category}</td>
                    <td>{r.likelihood}</td>
                    <td>{r.impact}</td>
                    <td><span className={lvl.cls}>{lvl.label}</span></td>
                    <td>{RISK_STATUS_AR[r.status] ?? r.status}</td>
                    <td>
                      {r.synced === false ? (
                        <span className="badge warn">بانتظار الإرسال</span>
                      ) : (
                        <span className="badge on">مُزامن</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>التدقيق الداخلي</h3>
        {canManage && (
          <button className="badge on" style={{ marginBottom: 8 }} onClick={() => setShowAuditForm((v) => !v)}>
            {showAuditForm ? "إلغاء" : "تدقيق جديد"}
          </button>
        )}
        {showAuditForm && canManage && (
          <div style={{ marginBottom: 12 }}>
            <div className="row">
              <div className="field">
                <label>عنوان التدقيق</label>
                <input
                  value={auditForm.title}
                  onChange={(e) => setAuditForm({ ...auditForm, title: e.target.value })}
                  placeholder="مثال: تدقيق الالتزام بمعايير مكافحة العدوى"
                />
              </div>
              <div className="field">
                <label>المعيار المرجعي</label>
                <input
                  value={auditForm.standard_ar}
                  onChange={(e) => setAuditForm({ ...auditForm, standard_ar: e.target.value })}
                  placeholder="مثال: معايير مكافحة العدوى الوطنية"
                />
              </div>
              <div className="field">
                <label>القسم</label>
                <select
                  value={auditForm.department_id}
                  onChange={(e) => setAuditForm({ ...auditForm, department_id: e.target.value })}
                >
                  <option value="">— بدون قسم محدد —</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>{d.name_ar}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>نطاق التدقيق</label>
                <input
                  value={auditForm.scope_ar}
                  onChange={(e) => setAuditForm({ ...auditForm, scope_ar: e.target.value })}
                />
              </div>
              <div className="field">
                <label>اسم المدقق</label>
                <input
                  value={auditForm.auditor_name_ar}
                  onChange={(e) => setAuditForm({ ...auditForm, auditor_name_ar: e.target.value })}
                />
              </div>
              <div className="field">
                <label>تاريخ التدقيق</label>
                <input
                  type="date"
                  value={auditForm.audit_date}
                  onChange={(e) => setAuditForm({ ...auditForm, audit_date: e.target.value })}
                />
              </div>
            </div>
            <button className="badge on" disabled={busy} onClick={() => void submitAudit()}>
              {busy ? "جارٍ الحفظ..." : "حفظ التدقيق"}
            </button>
          </div>
        )}
        {auditRows.length === 0 ? (
          <div className="empty">لا توجد تدقيقات مسجّلة بعد.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>الرمز</th>
                <th>العنوان</th>
                <th>المعيار</th>
                <th>التاريخ</th>
                <th>الحالة</th>
                <th>الدرجة</th>
                <th>المزامنة</th>
              </tr>
            </thead>
            <tbody>
              {auditRows.map((a) => (
                <tr key={a.id}>
                  <td>{a.code}</td>
                  <td>{a.title}</td>
                  <td>{a.standard_ar ?? "—"}</td>
                  <td>{a.audit_date ?? "—"}</td>
                  <td>{AUDIT_STATUS_AR[a.status] ?? a.status}</td>
                  <td>{a.score === null ? "—" : a.score}</td>
                  <td>
                    {a.synced === false ? (
                      <span className="badge warn">بانتظار الإرسال</span>
                    ) : (
                      <span className="badge on">مُزامن</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>خطط التحسين</h3>
        {canManage && (
          <button className="badge on" style={{ marginBottom: 8 }} onClick={() => setShowPlanForm((v) => !v)}>
            {showPlanForm ? "إلغاء" : "خطة جديدة"}
          </button>
        )}
        {showPlanForm && canManage && (
          <div style={{ marginBottom: 12 }}>
            <div className="row">
              <div className="field">
                <label>عنوان الخطة</label>
                <input
                  value={planForm.title}
                  onChange={(e) => setPlanForm({ ...planForm, title: e.target.value })}
                  placeholder="مثال: تقليل زمن الانتظار في الطوارئ"
                />
              </div>
              <div className="field">
                <label>القسم</label>
                <select
                  value={planForm.department_id}
                  onChange={(e) => setPlanForm({ ...planForm, department_id: e.target.value })}
                >
                  <option value="">— بدون قسم محدد —</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>{d.name_ar}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>المسؤول</label>
                <input
                  value={planForm.owner_name_ar}
                  onChange={(e) => setPlanForm({ ...planForm, owner_name_ar: e.target.value })}
                />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>الوضع الأساسي</label>
                <input
                  value={planForm.baseline_ar}
                  onChange={(e) => setPlanForm({ ...planForm, baseline_ar: e.target.value })}
                />
              </div>
              <div className="field">
                <label>المستهدف</label>
                <input
                  value={planForm.target_ar}
                  onChange={(e) => setPlanForm({ ...planForm, target_ar: e.target.value })}
                />
              </div>
              <div className="field">
                <label>تاريخ البدء</label>
                <input
                  type="date"
                  value={planForm.start_date}
                  onChange={(e) => setPlanForm({ ...planForm, start_date: e.target.value })}
                />
              </div>
              <div className="field">
                <label>تاريخ الاستحقاق</label>
                <input
                  type="date"
                  value={planForm.due_date}
                  onChange={(e) => setPlanForm({ ...planForm, due_date: e.target.value })}
                />
              </div>
            </div>
            <div className="field">
              <label>هدف الخطة</label>
              <textarea
                rows={2}
                value={planForm.objective_ar}
                onChange={(e) => setPlanForm({ ...planForm, objective_ar: e.target.value })}
              />
            </div>
            <button className="badge on" disabled={busy} onClick={() => void submitPlan()}>
              {busy ? "جارٍ الحفظ..." : "حفظ الخطة"}
            </button>
          </div>
        )}
        {planRows.length === 0 ? (
          <div className="empty">لا توجد خطط تحسين مسجّلة بعد.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>الرمز</th>
                <th>العنوان</th>
                <th>الاستحقاق</th>
                <th>الحالة</th>
                <th>المزامنة</th>
                <th>الخطوات</th>
              </tr>
            </thead>
            <tbody>
              {planRows.map((p) => (
                <Fragment key={p.id}>
                  <tr>
                    <td>{p.code}</td>
                    <td>{p.title}</td>
                    <td>{p.due_date ?? "—"}</td>
                    <td>{PLAN_STATUS_AR[p.status] ?? p.status}</td>
                    <td>
                      {p.synced === false ? (
                        <span className="badge warn">بانتظار الإرسال</span>
                      ) : (
                        <span className="badge on">مُزامن</span>
                      )}
                    </td>
                    <td>
                      <button className="badge" onClick={() => void togglePlan(p)}>
                        {openPlanId === p.id ? "إخفاء" : "عرض الخطوات"}
                      </button>
                    </td>
                  </tr>
                  {openPlanId === p.id && (
                    <tr>
                      <td colSpan={6}>
                        <div style={{ padding: "8px 0" }}>
                          {(planActions[p.id] ?? []).length === 0 ? (
                            <div className="empty">لا توجد خطوات بعد.</div>
                          ) : (
                            <table>
                              <thead>
                                <tr>
                                  <th>الخطوة</th>
                                  <th>المسؤول</th>
                                  <th>الاستحقاق</th>
                                  <th>الحالة</th>
                                  <th>المزامنة</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(planActions[p.id] ?? []).map((a) => (
                                  <tr key={a.id}>
                                    <td>{a.title}</td>
                                    <td>{a.owner_name_ar ?? "—"}</td>
                                    <td>{a.due_date ?? "—"}</td>
                                    <td>{PLAN_ACTION_STATUS_AR[a.status] ?? a.status}</td>
                                    <td>
                                      {a.synced === false ? (
                                        <span className="badge warn">بانتظار الإرسال</span>
                                      ) : (
                                        <span className="badge on">مُزامن</span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {canManage && (
                            <div className="row" style={{ marginTop: 8 }}>
                              <div className="field">
                                <label>خطوة جديدة</label>
                                <input
                                  value={actionForm.title}
                                  onChange={(e) => setActionForm({ ...actionForm, title: e.target.value })}
                                />
                              </div>
                              <div className="field">
                                <label>المسؤول</label>
                                <input
                                  value={actionForm.owner_name_ar}
                                  onChange={(e) => setActionForm({ ...actionForm, owner_name_ar: e.target.value })}
                                />
                              </div>
                              <div className="field">
                                <label>الاستحقاق</label>
                                <input
                                  type="date"
                                  value={actionForm.due_date}
                                  onChange={(e) => setActionForm({ ...actionForm, due_date: e.target.value })}
                                />
                              </div>
                              <div className="field">
                                <label>ملاحظة</label>
                                <input
                                  value={actionForm.note_ar}
                                  onChange={(e) => setActionForm({ ...actionForm, note_ar: e.target.value })}
                                />
                              </div>
                              <button className="badge on" disabled={busy} onClick={() => void submitPlanAction(p.id)}>
                                إضافة
                              </button>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="hint">
        تُعرض الحوادث والإجراءات والمخاطر والتدقيقات وخطط التحسين من المخزن المحلي والخادم معاً؛
        الصفوف «بانتظار الإرسال» أُنشئت دون اتصال وستُرسَل تلقائياً عند عودة الإنترنت. المستوى يُحسب
        على الخادم من الاحتمال × الأثر.
      </div>
    </div>
  );
}
