import { useCallback, useState } from "react";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";
import { hasPermission, useAuth } from "../auth";
import { Card, ErrorBox, Loading, Stat } from "../components/ui";
import {
  ACTION_STATUS_AR,
  AUDIT_STATUS_AR,
  CAPA_KIND_AR,
  CAPA_STATUS_AR,
  DOC_STATUS_AR,
  DOC_TYPE_AR,
  INCIDENT_STATUS_AR,
  INCIDENT_TYPE_AR,
  MEETING_STATUS_AR,
  PATIENT_HARM_AR,
  PLAN_STATUS_AR,
  PRIORITY_AR,
  RCA_CATEGORY_AR,
  RCA_METHOD_AR,
  RISK_CATEGORY_AR,
  RISK_STATUS_AR,
  SEVERITY_AR,
  SEVERITY_TONE,
  fmtDate,
  label,
  riskBand,
} from "../quality";
import type {
  Capa,
  ImprovementPlan,
  Incident,
  QualityAudit,
  QualityDocument,
  QualityMeeting,
  QualitySummary,
  Risk,
} from "../types";

type Tab =
  | "overview"
  | "incidents"
  | "capa"
  | "risks"
  | "audits"
  | "plans"
  | "documents"
  | "meetings";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "نظرة عامة" },
  { id: "incidents", label: "الحوادث وRCA" },
  { id: "capa", label: "الإجراءات CAPA" },
  { id: "risks", label: "سجل المخاطر" },
  { id: "audits", label: "التدقيق الداخلي" },
  { id: "plans", label: "خطط التحسين" },
  { id: "documents", label: "الوثائق والسياسات" },
  { id: "meetings", label: "اجتماعات الجودة" },
];

function SevBadge({ severity }: { severity: string }) {
  const tone = SEVERITY_TONE[severity] ?? "off";
  return <span className={`badge ${tone}`}>{label(SEVERITY_AR, severity)}</span>;
}

function StatusBadge({ map, code }: { map: Record<string, string>; code: string }) {
  const tone = code === "closed" || code === "verified" || code === "done" || code === "completed" || code === "approved" || code === "held"
    ? "on"
    : code === "cancelled" || code === "rejected" || code === "obsolete"
      ? "off"
      : code === "rca" || code === "capa" || code === "in_progress" || code === "under_review" || code === "under_review"
        ? "warn"
        : "bad";
  return <span className={`badge ${tone}`}>{label(map, code)}</span>;
}

export default function Quality() {
  const { me } = useAuth();
  const [tab, setTab] = useState<Tab>("overview");
  const canManage = hasPermission(me, "quality.manage");
  const scopedHospital = me?.scope_org.hospital_id ?? null;
  // Central users have no hospital scope; let them pick which hospital to review.
  const [pickedHospital, setPickedHospital] = useState<string>("");
  const hospitalId = scopedHospital ?? (pickedHospital || null);

  const loadHospitals = useCallback(() => api.hospitals(), []);
  const hospitals = useAsync(loadHospitals, []);

  return (
    <div>
      {!scopedHospital ? (
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="field">
            <label htmlFor="quality-hospital">المستشفى المعروض</label>
            <select
              id="quality-hospital"
              value={pickedHospital}
              onChange={(e) => setPickedHospital(e.target.value)}
            >
              <option value="">اختر مستشفى لعرض وحدات الجودة...</option>
              {(hospitals.data ?? []).map((h) => (
                <option key={h.id} value={h.id}>{h.name_ar}</option>
              ))}
            </select>
          </div>
        </div>
      ) : null}

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {!canManage ? (
        <div className="card" style={{ background: "#fff7ed", borderColor: "#fdba74" }}>
          وضع القراءة فقط: حسابك لا يملك صلاحية «إدارة الجودة»، فيعرض البيانات دون تعديل.
        </div>
      ) : null}
      {!hospitalId ? (
        <div className="empty">اختر مستشفى لعرض بيانات الجودة وسلامة المرضى.</div>
      ) : (
        <>
          {tab === "overview" ? <Overview hospitalId={hospitalId} /> : null}
          {tab === "incidents" ? <Incidents hospitalId={hospitalId} canManage={canManage} /> : null}
          {tab === "capa" ? <CapaTab hospitalId={hospitalId} canManage={canManage} /> : null}
          {tab === "risks" ? <Risks hospitalId={hospitalId} canManage={canManage} /> : null}
          {tab === "audits" ? <Audits hospitalId={hospitalId} canManage={canManage} /> : null}
          {tab === "plans" ? <Plans hospitalId={hospitalId} canManage={canManage} /> : null}
          {tab === "documents" ? <Documents hospitalId={hospitalId} canManage={canManage} /> : null}
          {tab === "meetings" ? <Meetings hospitalId={hospitalId} canManage={canManage} /> : null}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------
function Overview({ hospitalId }: { hospitalId: string | null }) {
  const load = useCallback(() => api.qualitySummary(hospitalId), [hospitalId]);
  const { data, loading, error } = useAsync<QualitySummary>(load, [hospitalId]);
  if (loading && !data) return <Loading what="ملخص الجودة" />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const sev = Object.entries(data.incidents_by_severity);
  return (
    <>
      <div className="stat-grid">
        <Stat label="إجمالي الحوادث" value={data.incidents_total} sub={`${data.incidents_open} مفتوحة`} />
        <Stat label="تحليل أسباب مفتوح" value={data.rca_open} />
        <Stat
          label="إجراءات CAPA"
          value={data.capa_total}
          sub={`${data.capa_open} مفتوحة · ${data.capa_overdue} متأخرة`}
        />
        <Stat label="مخاطر مرتفعة" value={data.risks_high} sub={`من ${data.risks_total}`} />
        <Stat label="تدقيقات مكتملة" value={data.audits_completed} sub={`من ${data.audits_total}`} />
        <Stat label="خطط تحسين نشطة" value={data.plans_active} />
        <Stat label="وثائق معتمدة" value={data.documents_approved} />
        <Stat label="قرارات مفتوحة" value={data.decisions_open} sub={`${data.meetings_held} اجتماع`} />
      </div>

      <Card title="توزيع الحوادث حسب الخطورة">
        {sev.length === 0 ? (
          <div className="empty">لا توجد حوادث مسجّلة.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>الخطورة</th>
                <th>العدد</th>
              </tr>
            </thead>
            <tbody>
              {sev.map(([k, v]) => (
                <tr key={k}>
                  <td>
                    <SevBadge severity={k} />
                  </td>
                  <td>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------------------
// Incidents (+ RCA)
// ---------------------------------------------------------------------------
function Incidents({ hospitalId, canManage }: { hospitalId: string | null; canManage: boolean }) {
  const load = useCallback(() => api.incidents(hospitalId), [hospitalId]);
  const { data, loading, error, reload } = useAsync<Incident[]>(load, [hospitalId]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    incident_type: "other",
    severity: "moderate",
    patient_harm: "none",
    description: "",
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.createIncident({ ...form, hospital_id: hospitalId });
      setForm({ title: "", incident_type: "other", severity: "moderate", patient_harm: "none", description: "" });
      setMsg("تم تسجيل الحادث.");
      reload();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Loading what="الحوادث" />;
  if (error) return <ErrorBox message={error} />;

  return (
    <>
      {canManage ? (
        <Card title="الإبلاغ عن حادث جديد">
          <form onSubmit={submit} className="row">
            <label>
              عنوان الحادث
              <input
                required
                minLength={3}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="وصف موجز للحادث"
              />
            </label>
            <label>
              النوع
              <select value={form.incident_type} onChange={(e) => setForm({ ...form, incident_type: e.target.value })}>
                {Object.entries(INCIDENT_TYPE_AR).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              الخطورة
              <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
                {Object.entries(SEVERITY_AR).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              الضرر على المريض
              <select value={form.patient_harm} onChange={(e) => setForm({ ...form, patient_harm: e.target.value })}>
                {Object.entries(PATIENT_HARM_AR).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              الوصف
              <textarea
                rows={2}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </label>
            <div>
              <button className="primary" type="submit" disabled={busy}>{busy ? "جارٍ الحفظ..." : "تسجيل الحادث"}</button>
            </div>
          </form>
          {msg ? <div className="badge on" style={{ marginTop: 8 }}>{msg}</div> : null}
        </Card>
      ) : null}

      <Card title={`قائمة الحوادث (${data?.length ?? 0})`}>
        {!data || data.length === 0 ? (
          <div className="empty">لا توجد حوادث.</div>
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الرمز</th>
                  <th>العنوان</th>
                  <th>النوع</th>
                  <th>الخطورة</th>
                  <th>الحالة</th>
                  <th>تاريخ الإبلاغ</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((i) => (
                  <tr key={i.id}>
                    <td>{i.code}</td>
                    <td>{i.title}</td>
                    <td>{label(INCIDENT_TYPE_AR, i.incident_type)}</td>
                    <td><SevBadge severity={i.severity} /></td>
                    <td><StatusBadge map={INCIDENT_STATUS_AR} code={i.status} /></td>
                    <td>{fmtDate(i.reported_at)}</td>
                    <td>
                      <button className="" onClick={() => setOpenId(openId === i.id ? null : i.id)}>
                        {openId === i.id ? "إخفاء" : "تفاصيل"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {openId ? <IncidentDetail incidentId={openId} canManage={canManage} /> : null}
    </>
  );
}

function IncidentDetail({ incidentId, canManage }: { incidentId: string; canManage: boolean }) {
  const load = useCallback(() => api.rca(incidentId).catch(() => null), [incidentId]);
  const { data, loading } = useAsync(load, [incidentId]);
  const [busy, setBusy] = useState(false);
  const [cause, setCause] = useState({ category: "process", description_ar: "", is_root_cause: false });
  const [note, setNote] = useState<string | null>(null);

  async function createRca() {
    setBusy(true);
    setNote(null);
    try {
      await api.createRca(incidentId, { method: "five_whys" });
      window.location.reload();
    } catch (e) {
      setNote(e instanceof Error ? e.message : "تعذّر الإنشاء.");
    } finally {
      setBusy(false);
    }
  }

  async function addCause(e: React.FormEvent) {
    e.preventDefault();
    if (!data) return;
    setBusy(true);
    setNote(null);
    try {
      await api.addRcaCause(data.rca.id, cause);
      setCause({ category: "process", description_ar: "", is_root_cause: false });
      window.location.reload();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "تعذّر الإضافة.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading what="تحليل الأسباب" />;

  if (!data) {
    return (
      <Card title="تحليل الأسباب الجذرية (RCA)">
        <div className="empty">لا يوجد تحليل أسباب جذرية لهذا الحادث بعد.</div>
        {canManage ? (
          <button onClick={createRca} disabled={busy}>{busy ? "جارٍ الإنشاء..." : "بدء تحليل الأسباب الجذرية"}</button>
        ) : null}
        {note ? <div className="badge bad" style={{ marginTop: 8 }}>{note}</div> : null}
      </Card>
    );
  }

  return (
    <Card title={`تحليل الأسباب الجذرية — ${label(RCA_METHOD_AR, data.rca.method)}`}>
      <div className="row" style={{ gap: 16, flexWrap: "wrap" }}>
        <div><strong>الحالة:</strong> {data.rca.status}</div>
        <div><strong>الفريق:</strong> {data.rca.team_ar ?? "—"}</div>
      </div>
      {data.rca.findings_ar ? <p>{data.rca.findings_ar}</p> : null}

      <h4>الأسباب ({data.causes.length})</h4>
      {data.causes.length === 0 ? (
        <div className="empty">لم تُسجَّل أسباب بعد.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>التصنيف</th>
              <th>الوصف</th>
              <th>سبب جذري؟</th>
            </tr>
          </thead>
          <tbody>
            {data.causes.map((c) => (
              <tr key={c.id}>
                <td>{label(RCA_CATEGORY_AR, c.category)}</td>
                <td>{c.description_ar}</td>
                <td>{c.is_root_cause ? <span className="badge bad">جذري</span> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canManage ? (
        <form onSubmit={addCause} className="row" style={{ marginTop: 12 }}>
          <label>
            التصنيف
            <select value={cause.category} onChange={(e) => setCause({ ...cause, category: e.target.value })}>
              {Object.entries(RCA_CATEGORY_AR).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            وصف السبب
            <input
              required
              minLength={3}
              value={cause.description_ar}
              onChange={(e) => setCause({ ...cause, description_ar: e.target.value })}
            />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={cause.is_root_cause}
              onChange={(e) => setCause({ ...cause, is_root_cause: e.target.checked })}
            />
            سبب جذري
          </label>
          <div>
            <button className="primary" type="submit" disabled={busy}>إضافة السبب</button>
          </div>
        </form>
      ) : null}
      {note ? <div className="badge bad" style={{ marginTop: 8 }}>{note}</div> : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// CAPA
// ---------------------------------------------------------------------------
function CapaTab({ hospitalId, canManage }: { hospitalId: string | null; canManage: boolean }) {
  const [overdueOnly, setOverdueOnly] = useState(false);
  const load = useCallback(() => api.capa(hospitalId, overdueOnly), [hospitalId, overdueOnly]);
  const { data, loading, error, reload } = useAsync<Capa[]>(load, [hospitalId, overdueOnly]);
  const [form, setForm] = useState({ title: "", kind: "corrective", priority: "medium", due_date: "", owner_name_ar: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.createCapa({
        ...form,
        due_date: form.due_date || null,
        hospital_id: hospitalId,
      });
      setForm({ title: "", kind: "corrective", priority: "medium", due_date: "", owner_name_ar: "" });
      setMsg("تم إنشاء الإجراء.");
      reload();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  }

  async function advance(id: string, status: string) {
    await api.updateCapa(id, { status });
    reload();
  }

  if (loading && !data) return <Loading what="الإجراءات" />;
  if (error) return <ErrorBox message={error} />;

  return (
    <>
      {canManage ? (
        <Card title="إجراء تصحيحي / وقائي جديد">
          <form onSubmit={submit} className="row">
            <label>
              العنوان
              <input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label>
              النوع
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {Object.entries(CAPA_KIND_AR).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
              </select>
            </label>
            <label>
              الأولوية
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {Object.entries(PRIORITY_AR).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
              </select>
            </label>
            <label>
              تاريخ الاستحقاق
              <input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </label>
            <label>
              المسؤول
              <input value={form.owner_name_ar} onChange={(e) => setForm({ ...form, owner_name_ar: e.target.value })} />
            </label>
            <div>
              <button className="primary" type="submit" disabled={busy}>{busy ? "جارٍ الحفظ..." : "إنشاء الإجراء"}</button>
            </div>
          </form>
          {msg ? <div className="badge on" style={{ marginTop: 8 }}>{msg}</div> : null}
        </Card>
      ) : null}

      <div className="toolbar">
        <label style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ink)" }}>
          <input type="checkbox" style={{ width: "auto" }} checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} />
          المتأخرة فقط
        </label>
      </div>

      <Card title={`الإجراءات (${data?.length ?? 0})`}>
        {!data || data.length === 0 ? (
          <div className="empty">لا توجد إجراءات.</div>
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>العنوان</th>
                  <th>النوع</th>
                  <th>الأولوية</th>
                  <th>الاستحقاق</th>
                  <th>الحالة</th>
                  <th>المسؤول</th>
                  {canManage ? <th /> : null}
                </tr>
              </thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {c.title} {c.is_overdue ? <span className="badge bad">متأخر</span> : null}
                    </td>
                    <td>{label(CAPA_KIND_AR, c.kind)}</td>
                    <td>{label(PRIORITY_AR, c.priority)}</td>
                    <td>{fmtDate(c.due_date)}</td>
                    <td><StatusBadge map={CAPA_STATUS_AR} code={c.status} /></td>
                    <td>{c.owner_name_ar ?? "—"}</td>
                    {canManage ? (
                      <td>
                        {c.status !== "verified" ? (
                          <button className="" onClick={() => advance(c.id, c.status === "open" ? "in_progress" : c.status === "in_progress" ? "done" : "verified")}>
                            تقدّم
                          </button>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------------------
// Risks
// ---------------------------------------------------------------------------
function Risks({ hospitalId, canManage }: { hospitalId: string | null; canManage: boolean }) {
  const load = useCallback(() => api.risks(hospitalId), [hospitalId]);
  const { data, loading, error, reload } = useAsync<Risk[]>(load, [hospitalId]);
  const [form, setForm] = useState({ title: "", category: "clinical", likelihood: 3, impact: 3, mitigation_ar: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.createRisk({ ...form, hospital_id: hospitalId });
      setForm({ title: "", category: "clinical", likelihood: 3, impact: 3, mitigation_ar: "" });
      setMsg("تمت إضافة الخطر.");
      reload();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Loading what="سجل المخاطر" />;
  if (error) return <ErrorBox message={error} />;

  return (
    <>
      {canManage ? (
        <Card title="إضافة خطر إلى السجل">
          <form onSubmit={submit} className="row">
            <label>
              وصف الخطر
              <input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label>
              التصنيف
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {Object.entries(RISK_CATEGORY_AR).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
              </select>
            </label>
            <label>
              الاحتمالية (1–5)
              <input type="number" min={1} max={5} value={form.likelihood} onChange={(e) => setForm({ ...form, likelihood: Number(e.target.value) })} />
            </label>
            <label>
              الأثر (1–5)
              <input type="number" min={1} max={5} value={form.impact} onChange={(e) => setForm({ ...form, impact: Number(e.target.value) })} />
            </label>
            <label>
              إجراءات التخفيف
              <textarea rows={2} value={form.mitigation_ar} onChange={(e) => setForm({ ...form, mitigation_ar: e.target.value })} />
            </label>
            <div>
              <button className="primary" type="submit" disabled={busy}>{busy ? "جارٍ الحفظ..." : "إضافة الخطر"}</button>
            </div>
          </form>
          {msg ? <div className="badge on" style={{ marginTop: 8 }}>{msg}</div> : null}
        </Card>
      ) : null}

      <Card title={`سجل المخاطر (${data?.length ?? 0})`}>
        {!data || data.length === 0 ? (
          <div className="empty">لا توجد مخاطر مسجّلة.</div>
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الرمز</th>
                  <th>الخطر</th>
                  <th>التصنيف</th>
                  <th>الاحتمالية</th>
                  <th>الأثر</th>
                  <th>الدرجة</th>
                  <th>الحالة</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => {
                  const band = riskBand(r.score);
                  return (
                    <tr key={r.id}>
                      <td>{r.code}</td>
                      <td>{r.title}</td>
                      <td>{label(RISK_CATEGORY_AR, r.category)}</td>
                      <td>{r.likelihood}</td>
                      <td>{r.impact}</td>
                      <td><span className={`badge ${band.tone}`}>{r.score} — {band.label}</span></td>
                      <td><StatusBadge map={RISK_STATUS_AR} code={r.status} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------------------
// Audits
// ---------------------------------------------------------------------------
function Audits({ hospitalId, canManage }: { hospitalId: string | null; canManage: boolean }) {
  const load = useCallback(() => api.qualityAudits(hospitalId), [hospitalId]);
  const { data, loading, error, reload } = useAsync<QualityAudit[]>(load, [hospitalId]);
  const [form, setForm] = useState({ title: "", standard_ar: "", audit_date: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.createQualityAudit({ ...form, audit_date: form.audit_date || null, hospital_id: hospitalId });
      setForm({ title: "", standard_ar: "", audit_date: "" });
      setMsg("تمت جدولة التدقيق.");
      reload();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Loading what="التدقيق" />;
  if (error) return <ErrorBox message={error} />;

  return (
    <>
      {canManage ? (
        <Card title="تدقيق داخلي جديد">
          <form onSubmit={submit} className="row">
            <label>
              عنوان التدقيق
              <input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label>
              المعيار
              <input value={form.standard_ar} onChange={(e) => setForm({ ...form, standard_ar: e.target.value })} />
            </label>
            <label>
              تاريخ التدقيق
              <input type="date" value={form.audit_date} onChange={(e) => setForm({ ...form, audit_date: e.target.value })} />
            </label>
            <div>
              <button className="primary" type="submit" disabled={busy}>{busy ? "جارٍ الحفظ..." : "جدولة"}</button>
            </div>
          </form>
          {msg ? <div className="badge on" style={{ marginTop: 8 }}>{msg}</div> : null}
        </Card>
      ) : null}

      <Card title={`التدقيقات (${data?.length ?? 0})`}>
        {!data || data.length === 0 ? (
          <div className="empty">لا توجد تدقيقات.</div>
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الرمز</th>
                  <th>العنوان</th>
                  <th>المعيار</th>
                  <th>التاريخ</th>
                  <th>النسبة</th>
                  <th>الحالة</th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id}>
                    <td>{a.code}</td>
                    <td>{a.title}</td>
                    <td>{a.standard_ar ?? "—"}</td>
                    <td>{fmtDate(a.audit_date)}</td>
                    <td>{a.score === null ? "—" : `${a.score}%`}</td>
                    <td><StatusBadge map={AUDIT_STATUS_AR} code={a.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------------------
// Improvement plans
// ---------------------------------------------------------------------------
function Plans({ hospitalId, canManage }: { hospitalId: string | null; canManage: boolean }) {
  const load = useCallback(() => api.qualityPlans(hospitalId), [hospitalId]);
  const { data, loading, error, reload } = useAsync<ImprovementPlan[]>(load, [hospitalId]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", objective_ar: "", due_date: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.createQualityPlan({ ...form, due_date: form.due_date || null, hospital_id: hospitalId, status: "active" });
      setForm({ title: "", objective_ar: "", due_date: "" });
      setMsg("تم إنشاء الخطة.");
      reload();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Loading what="خطط التحسين" />;
  if (error) return <ErrorBox message={error} />;

  return (
    <>
      {canManage ? (
        <Card title="خطة تحسين جديدة">
          <form onSubmit={submit} className="row">
            <label>
              عنوان الخطة
              <input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label>
              الهدف
              <textarea rows={2} value={form.objective_ar} onChange={(e) => setForm({ ...form, objective_ar: e.target.value })} />
            </label>
            <label>
              تاريخ الاستحقاق
              <input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
            </label>
            <div>
              <button className="primary" type="submit" disabled={busy}>{busy ? "جارٍ الحفظ..." : "إنشاء الخطة"}</button>
            </div>
          </form>
          {msg ? <div className="badge on" style={{ marginTop: 8 }}>{msg}</div> : null}
        </Card>
      ) : null}

      <Card title={`خطط التحسين (${data?.length ?? 0})`}>
        {!data || data.length === 0 ? (
          <div className="empty">لا توجد خطط.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>الرمز</th>
                <th>العنوان</th>
                <th>الاستحقاق</th>
                <th>الحالة</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id}>
                  <td>{p.code}</td>
                  <td>{p.title}</td>
                  <td>{fmtDate(p.due_date)}</td>
                  <td><StatusBadge map={PLAN_STATUS_AR} code={p.status} /></td>
                  <td>
                    <button className="" onClick={() => setOpenId(openId === p.id ? null : p.id)}>
                      {openId === p.id ? "إخفاء" : "الإجراءات"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {openId ? <PlanDetail planId={openId} canManage={canManage} /> : null}
    </>
  );
}

function PlanDetail({ planId, canManage }: { planId: string; canManage: boolean }) {
  const load = useCallback(() => api.qualityPlan(planId), [planId]);
  const { data, loading } = useAsync(load, [planId]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.addPlanAction(planId, { title });
      setTitle("");
      window.location.reload();
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading what="تفاصيل الخطة" />;
  if (!data) return null;
  return (
    <Card title={`إجراءات الخطة ${data.plan.code}`}>
      {data.plan.objective_ar ? <p>{data.plan.objective_ar}</p> : null}
      {data.actions.length === 0 ? (
        <div className="empty">لا توجد إجراءات.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>الإجراء</th>
              <th>المسؤول</th>
              <th>الاستحقاق</th>
              <th>الحالة</th>
            </tr>
          </thead>
          <tbody>
            {data.actions.map((a) => (
              <tr key={a.id}>
                <td>{a.title}</td>
                <td>{a.owner_name_ar ?? "—"}</td>
                <td>{fmtDate(a.due_date)}</td>
                <td><StatusBadge map={ACTION_STATUS_AR} code={a.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canManage ? (
        <form onSubmit={add} className="row" style={{ marginTop: 12 }}>
          <label>
            إجراء جديد
            <input required minLength={3} value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <div>
            <button className="primary" type="submit" disabled={busy}>إضافة</button>
          </div>
        </form>
      ) : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------
function Documents({ hospitalId, canManage }: { hospitalId: string | null; canManage: boolean }) {
  const load = useCallback(() => api.qualityDocuments(hospitalId), [hospitalId]);
  const { data, loading, error, reload } = useAsync<QualityDocument[]>(load, [hospitalId]);
  const [form, setForm] = useState({ title: "", doc_type: "policy", version: "1.0" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.createQualityDocument({ ...form, hospital_id: hospitalId });
      setForm({ title: "", doc_type: "policy", version: "1.0" });
      setMsg("تمت إضافة الوثيقة.");
      reload();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  }

  async function approve(id: string) {
    await api.updateQualityDocument(id, { status: "approved" });
    reload();
  }

  if (loading && !data) return <Loading what="الوثائق" />;
  if (error) return <ErrorBox message={error} />;

  return (
    <>
      {canManage ? (
        <Card title="وثيقة / سياسة جديدة">
          <form onSubmit={submit} className="row">
            <label>
              العنوان
              <input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label>
              النوع
              <select value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })}>
                {Object.entries(DOC_TYPE_AR).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
              </select>
            </label>
            <label>
              الإصدار
              <input value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} />
            </label>
            <div>
              <button className="primary" type="submit" disabled={busy}>{busy ? "جارٍ الحفظ..." : "إضافة"}</button>
            </div>
          </form>
          {msg ? <div className="badge on" style={{ marginTop: 8 }}>{msg}</div> : null}
        </Card>
      ) : null}

      <Card title={`الوثائق (${data?.length ?? 0})`}>
        {!data || data.length === 0 ? (
          <div className="empty">لا توجد وثائق.</div>
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الرمز</th>
                  <th>العنوان</th>
                  <th>النوع</th>
                  <th>الإصدار</th>
                  <th>الحالة</th>
                  {canManage ? <th /> : null}
                </tr>
              </thead>
              <tbody>
                {data.map((d) => (
                  <tr key={d.id}>
                    <td>{d.code}</td>
                    <td>{d.title}</td>
                    <td>{label(DOC_TYPE_AR, d.doc_type)}</td>
                    <td>{d.version}</td>
                    <td><StatusBadge map={DOC_STATUS_AR} code={d.status} /></td>
                    {canManage ? (
                      <td>
                        {d.status !== "approved" ? (
                          <button className="" onClick={() => approve(d.id)}>اعتماد</button>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ---------------------------------------------------------------------------
// Meetings
// ---------------------------------------------------------------------------
function Meetings({ hospitalId, canManage }: { hospitalId: string | null; canManage: boolean }) {
  const load = useCallback(() => api.qualityMeetings(hospitalId), [hospitalId]);
  const { data, loading, error, reload } = useAsync<QualityMeeting[]>(load, [hospitalId]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", meeting_date: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api.createQualityMeeting({ ...form, meeting_date: form.meeting_date || null, hospital_id: hospitalId });
      setForm({ title: "", meeting_date: "" });
      setMsg("تمت جدولة الاجتماع.");
      reload();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Loading what="الاجتماعات" />;
  if (error) return <ErrorBox message={error} />;

  return (
    <>
      {canManage ? (
        <Card title="اجتماع جودة جديد">
          <form onSubmit={submit} className="row">
            <label>
              عنوان الاجتماع
              <input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label>
              التاريخ
              <input type="date" value={form.meeting_date} onChange={(e) => setForm({ ...form, meeting_date: e.target.value })} />
            </label>
            <div>
              <button className="primary" type="submit" disabled={busy}>{busy ? "جارٍ الحفظ..." : "جدولة"}</button>
            </div>
          </form>
          {msg ? <div className="badge on" style={{ marginTop: 8 }}>{msg}</div> : null}
        </Card>
      ) : null}

      <Card title={`الاجتماعات (${data?.length ?? 0})`}>
        {!data || data.length === 0 ? (
          <div className="empty">لا توجد اجتماعات.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>العنوان</th>
                <th>التاريخ</th>
                <th>رئيس الاجتماع</th>
                <th>الحالة</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((m) => (
                <tr key={m.id}>
                  <td>{m.title}</td>
                  <td>{fmtDate(m.meeting_date)}</td>
                  <td>{m.chair_name_ar ?? "—"}</td>
                  <td><StatusBadge map={MEETING_STATUS_AR} code={m.status} /></td>
                  <td>
                    <button className="" onClick={() => setOpenId(openId === m.id ? null : m.id)}>
                      {openId === m.id ? "إخفاء" : "القرارات"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {openId ? <MeetingDetailView meetingId={openId} canManage={canManage} /> : null}
    </>
  );
}

function MeetingDetailView({ meetingId, canManage }: { meetingId: string; canManage: boolean }) {
  const load = useCallback(() => api.qualityMeeting(meetingId), [meetingId]);
  const { data, loading } = useAsync(load, [meetingId]);
  const [decision, setDecision] = useState("");
  const [busy, setBusy] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.addMeetingDecision(meetingId, { decision_ar: decision });
      setDecision("");
      window.location.reload();
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading what="قرارات الاجتماع" />;
  if (!data) return null;
  return (
    <Card title={`قرارات الاجتماع`}>
      {data.meeting.minutes_ar ? <p>{data.meeting.minutes_ar}</p> : null}
      {data.decisions.length === 0 ? (
        <div className="empty">لا توجد قرارات.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>القرار</th>
              <th>المسؤول</th>
              <th>الاستحقاق</th>
              <th>الحالة</th>
            </tr>
          </thead>
          <tbody>
            {data.decisions.map((d) => (
              <tr key={d.id}>
                <td>{d.decision_ar}</td>
                <td>{d.owner_name_ar ?? "—"}</td>
                <td>{fmtDate(d.due_date)}</td>
                <td><StatusBadge map={ACTION_STATUS_AR} code={d.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canManage ? (
        <form onSubmit={add} className="row" style={{ marginTop: 12 }}>
          <label>
            قرار جديد
            <input required minLength={3} value={decision} onChange={(e) => setDecision(e.target.value)} />
          </label>
          <div>
            <button className="primary" type="submit" disabled={busy}>إضافة</button>
          </div>
        </form>
      ) : null}
    </Card>
  );
}
