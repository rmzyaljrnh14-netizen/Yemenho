import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { hasPermission, useAuth } from "../auth";
import { desktop, isDesktop } from "../desktop";
import type {
  AssignedIndicator,
  Department,
  Hospital,
  Indicator,
  PeriodDetail,
  PeriodStatus,
  ReportingPeriod,
} from "../types";

const DESK = isDesktop();

function newId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const STATUS_LABEL: Record<PeriodStatus, string> = {
  draft: "مسودة",
  submitted: "مُرسلة للمراجعة",
  reviewed: "مُراجعة",
  approved: "معتمدة",
  returned: "مُعادة للتعديل",
};

const STATUS_CLASS: Record<PeriodStatus, string> = {
  draft: "badge",
  submitted: "badge warn",
  reviewed: "badge warn",
  approved: "badge on",
  returned: "badge off",
};

const AR_MONTHS = [
  "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
  "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
];

function periodLabel(p: ReportingPeriod): string {
  if (p.period_type === "monthly" && p.month) return `${AR_MONTHS[p.month - 1]} ${p.year}`;
  if (p.period_type === "quarterly" && p.quarter) return `الربع ${p.quarter} — ${p.year}`;
  return `${p.year}`;
}

// ---- Offline adapters: turn locally stored records into the same shapes the
// online pages use, so the entry form behaves identically without a connection.

function localPeriod(raw: Record<string, unknown>): ReportingPeriod {
  return {
    id: String(raw.id),
    hospital_id: String(raw.hospital_id ?? ""),
    period_type: (raw.period_type as ReportingPeriod["period_type"]) ?? "monthly",
    year: Number(raw.year ?? 0),
    month: (raw.month as number | null) ?? null,
    quarter: (raw.quarter as number | null) ?? null,
    status: (raw.status as PeriodStatus) ?? "draft",
    note: null,
    submitted_at: null,
    reviewed_at: null,
    approved_at: null,
    returned_at: null,
    created_at: "",
    updated_at: "",
  };
}

function localAssigned(
  assignments: Record<string, unknown>[],
  indicators: Indicator[],
): AssignedIndicator[] {
  const byId = new Map(indicators.map((i) => [i.id, i]));
  const out: AssignedIndicator[] = [];
  for (const a of assignments) {
    const indicator = byId.get(String(a.indicator_id));
    if (!indicator) continue;
    out.push({
      assignment_id: String(a.id),
      indicator,
      department_id: (a.department_id as string | null) ?? null,
      target_override: (a.target_override as number | null) ?? null,
    });
  }
  return out;
}

function localDetail(periodId: string, values: Record<string, unknown>[]): PeriodDetail {
  return {
    period: null as unknown as ReportingPeriod,
    values: values.map((v) => ({
      id: String(v.id),
      period_id: periodId,
      indicator_id: String(v.indicator_id),
      department_id: (v.department_id as string | null) ?? null,
      numerator: (v.numerator as number | null) ?? null,
      denominator: (v.denominator as number | null) ?? null,
      value: (v.value as number | null) ?? null,
      value_type: (v.value_type === "entered" ? "entered" : "computed") as "computed" | "entered",
      note: (v.note as string | null) ?? null,
      updated_at: "",
      assessment: {
        status: (["good", "warning", "poor", "unknown"].includes(String(v.assessment))
          ? String(v.assessment)
          : "unknown") as "good" | "warning" | "poor" | "unknown",
        label_ar: String(v.assessment_ar ?? "غير محسوب"),
        message_ar: "",
      },
    })),
  };
}

interface Draft {
  numerator: string;
  denominator: string;
  entered: string;
}

export default function DataEntry() {
  const { me } = useAuth();
  const canEnter = hasPermission(me, "indicator.enter");
  const canSubmit = hasPermission(me, "period.submit");
  const canReview = hasPermission(me, "period.review");
  const canApprove = hasPermission(me, "period.approve");

  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [hospital, setHospital] = useState<Hospital | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [periods, setPeriods] = useState<ReportingPeriod[]>([]);
  const [period, setPeriod] = useState<ReportingPeriod | null>(null);
  const [assigned, setAssigned] = useState<AssignedIndicator[]>([]);
  const [detail, setDetail] = useState<PeriodDetail | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const [localIds, setLocalIds] = useState<Set<string>>(new Set());

  // New-period form
  const now = new Date();
  const [newYear, setNewYear] = useState(now.getFullYear());
  const [newMonth, setNewMonth] = useState(now.getMonth() + 1);

  const loadPeriods = useCallback(async (h: Hospital) => {
    try {
      const list = await api.periods(h.id);
      setPeriods(list);
      setPeriod((prev) => list.find((p) => p.id === prev?.id) ?? list[0] ?? null);
      setOffline(false);
    } catch (e) {
      // Offline fallback: show the periods created on this device.
      if (!DESK) throw e;
      const local = (await desktop.listPeriods(h.id)) ?? [];
      const list = local.map(localPeriod);
      setPeriods(list);
      setPeriod((prev) => list.find((p) => p.id === prev?.id) ?? list[0] ?? null);
      setOffline(true);
    }
  }, []);

  const loadDetail = useCallback(async (p: ReportingPeriod) => {
    try {
      const d = await api.periodDetail(p.id);
      setDetail(d);
      setLocalIds(new Set());
      const next: Record<string, Draft> = {};
      for (const v of d.values) {
        next[`${v.indicator_id}:${v.department_id ?? ""}`] = {
          numerator: v.numerator != null ? String(v.numerator) : "",
          denominator: v.denominator != null ? String(v.denominator) : "",
          entered: v.value != null && v.value_type === "entered" ? String(v.value) : "",
        };
      }
      setDrafts(next);
    } catch (e) {
      if (!DESK) throw e;
      const values = (await desktop.listValues(p.id)) ?? [];
      setDetail(localDetail(p.id, values));
      const next: Record<string, Draft> = {};
      for (const v of values) {
        next[`${String(v.indicator_id)}:${(v.department_id as string | null) ?? ""}`] = {
          numerator: v.numerator != null ? String(v.numerator) : "",
          denominator: v.denominator != null ? String(v.denominator) : "",
          entered: v.value != null && v.value_type === "entered" ? String(v.value) : "",
        };
      }
      setDrafts(next);
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const list = await api.hospitals();
        setHospitals(list);
        setHospital(list[0] ?? null);
        if (DESK) await desktop.cacheHospitals(list);
      } catch (e) {
        if (DESK) {
          const local = (await desktop.listHospitals()) ?? [];
          const list = local.map((h) => ({
            id: String(h.id),
            name_ar: String(h.name_ar ?? ""),
            code: String(h.code ?? ""),
            governorate_id: (h.governorate_id as string | null) ?? null,
            organization_id: null,
            is_active: true,
          }));
          if (list.length > 0) {
            setHospitals(list);
            setHospital(list[0]);
            setOffline(true);
            return;
          }
        }
        setError(e instanceof Error ? e.message : "تعذّر التحميل.");
      }
    })();
  }, []);

  useEffect(() => {
    if (!hospital) return;
    (async () => {
      try {
        setError(null);
        const [assigns, depts] = await Promise.all([
          api.assignedIndicators(hospital.id),
          api.departments(hospital.id),
        ]);
        setAssigned(assigns);
        setDepartments(depts);
        if (DESK) {
          await desktop.cacheDepartments(depts);
          await desktop.cacheAssignments(
            assigns.map((a) => ({
              id: a.assignment_id,
              indicator_id: a.indicator.id,
              department_id: a.department_id,
              target_override: a.target_override,
            })),
          );
        }
        await loadPeriods(hospital);
      } catch (e) {
        if (!DESK) {
          setError(e instanceof Error ? e.message : "تعذّر تحميل بيانات المستشفى.");
          return;
        }
        // Offline: rebuild the entry form from the cached reference data.
        const [rawAssigns, rawDepts, indicators] = await Promise.all([
          desktop.listAssignments(),
          desktop.listDepartments(),
          desktop.localLibrary(),
        ]);
        setAssigned(localAssigned(rawAssigns ?? [], (indicators ?? []) as unknown as Indicator[]));
        setDepartments(
          (rawDepts ?? []).map((d) => ({
            id: String(d.id),
            hospital_id: String(d.hospital_id ?? ""),
            name_ar: String(d.name_ar ?? ""),
            code: (d.code as string | null) ?? null,
            is_active: true,
          })),
        );
        await loadPeriods(hospital);
      }
    })();
  }, [hospital, loadPeriods]);

  useEffect(() => {
    if (!period) {
      setDetail(null);
      return;
    }
    (async () => {
      try {
        setError(null);
        await loadDetail(period);
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل الفترة.");
      }
    })();
  }, [period, loadDetail]);

  const editable = period != null && (period.status === "draft" || period.status === "returned");

  function setDraft(key: string, patch: Partial<Draft>) {
    setDrafts((prev) => {
      const base: Draft = prev[key] ?? { numerator: "", denominator: "", entered: "" };
      return { ...prev, [key]: { ...base, ...patch } };
    });
  }

  async function createPeriod(e: React.FormEvent) {
    e.preventDefault();
    if (!hospital) return;
    setBusy(true);
    setError(null);
    try {
      const p = await api.createPeriod({
        hospital_id: hospital.id,
        period_type: "monthly",
        year: newYear,
        month: newMonth,
      });
      await loadPeriods(hospital);
      setPeriod(p);
    } catch (err) {
      if (DESK) {
        // Offline: create it locally and queue it for sync.
        try {
          const periodId = newId();
          await desktop.createPeriod({
            period_id: periodId,
            hospital_id: hospital.id,
            period_type: "monthly",
            year: newYear,
            month: newMonth,
          });
          await desktop.setHospital(hospital.id);
          await loadPeriods(hospital);
          setPeriod(localPeriod({ id: periodId, hospital_id: hospital.id, period_type: "monthly", year: newYear, month: newMonth, status: "draft" }));
          setOffline(true);
          setNotice("أُنشئت الفترة محلياً وستُرسَل عند عودة الاتصال.");
          return;
        } catch {
          /* fall through to the online error */
        }
      }
      setError(err instanceof Error ? err.message : "تعذّر إنشاء الفترة.");
    } finally {
      setBusy(false);
    }
  }

  async function saveValue(a: AssignedIndicator) {
    if (!period) return;
    const key = `${a.indicator.id}:${a.department_id ?? ""}`;
    const d = drafts[key] ?? { numerator: "", denominator: "", entered: "" };
    setBusy(true);
    setError(null);
    setNotice(null);
    const isDirect = ["count", "sum", "entered"].includes(a.indicator.computation);
    const body: Record<string, unknown> = {
      indicator_id: a.indicator.id,
      department_id: a.department_id,
    };
    if (isDirect) {
      body.entered_value = d.entered === "" ? null : Number(d.entered);
    } else {
      body.numerator = d.numerator === "" ? null : Number(d.numerator);
      body.denominator = d.denominator === "" ? null : Number(d.denominator);
    }
    try {
      await api.upsertValue(period.id, body as never);
      await loadDetail(period);
      setNotice(`تم حفظ قيمة «${a.indicator.name_ar}».`);
    } catch (err) {
      if (!DESK) {
        setError(err instanceof Error ? err.message : "تعذّر الحفظ.");
        return;
      }
      // Offline: compute and store locally, then queue the op for sync.
      try {
        const existingId = localIds.has(key) ? detail?.values.find((v) => `${v.indicator_id}:${v.department_id ?? ""}` === key)?.id : undefined;
        const res = await desktop.saveValue({
          value_id: existingId ?? newId(),
          period_id: period.id,
          indicator_id: a.indicator.id,
          department_id: a.department_id,
          numerator: isDirect ? null : (d.numerator === "" ? null : Number(d.numerator)),
          denominator: isDirect ? null : (d.denominator === "" ? null : Number(d.denominator)),
          entered_value: isDirect ? (d.entered === "" ? null : Number(d.entered)) : null,
          computation: a.indicator.computation,
          multiplier: a.indicator.multiplier,
          direction: a.indicator.direction,
          target_value: a.target_override ?? a.indicator.target_value,
          acceptable_min: a.indicator.acceptable_min,
          acceptable_max: a.indicator.acceptable_max,
        });
        const valueId = String(res?.value_id ?? "");
        setLocalIds((prev) => new Set(prev).add(key));
        setDetail((prev) => {
          const values = (prev?.values ?? []).filter((v) => `${v.indicator_id}:${v.department_id ?? ""}` !== key);
          values.push({
            id: valueId,
            period_id: period.id,
            indicator_id: a.indicator.id,
            department_id: a.department_id,
            numerator: isDirect ? null : (d.numerator === "" ? null : Number(d.numerator)),
            denominator: isDirect ? null : (d.denominator === "" ? null : Number(d.denominator)),
            value: (res?.value as number | null) ?? null,
            value_type: (res?.value_type === "entered" ? "entered" : "computed") as "computed" | "entered",
            note: null,
            updated_at: "",
            assessment: {
              status: (["good", "warning", "poor", "unknown"].includes(String(res?.assessment))
                ? String(res?.assessment)
                : "unknown") as "good" | "warning" | "poor" | "unknown",
              label_ar: String(res?.assessment_ar ?? "غير محسوب"),
              message_ar: "",
            },
          });
          return { period: prev?.period ?? (null as unknown as ReportingPeriod), values };
        });
        setOffline(true);
        setNotice(`حُفظت قيمة «${a.indicator.name_ar}» محلياً وستُرسَل عند عودة الاتصال.`);
      } catch (offlineErr) {
        setError(offlineErr instanceof Error ? offlineErr.message : "تعذّر الحفظ.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function doAction(action: "submit" | "review" | "approve" | "return") {
    if (!period || !hospital) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await api.periodAction(period.id, action);
      setNotice(`تم تحديث حالة الفترة إلى «${STATUS_LABEL[updated.status]}».`);
      await loadPeriods(hospital);
      setPeriod(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذّر تنفيذ الإجراء.");
    } finally {
      setBusy(false);
    }
  }

  const valuesByKey = new Map(
    (detail?.values ?? []).map((v) => [`${v.indicator_id}:${v.department_id ?? ""}`, v]),
  );
  const deptName = new Map(departments.map((d) => [d.id, d.name_ar]));
  const sortedAssigned = [...assigned].sort((a, b) => {
    if (a.indicator.code !== b.indicator.code) return a.indicator.code.localeCompare(b.indicator.code);
    return (a.department_id ?? "").localeCompare(b.department_id ?? "");
  });

  return (
    <div>
      <div className="card">
        <div className="row" style={{ flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
          <div className="field">
            <label>المستشفى</label>
            <select
              value={hospital?.id ?? ""}
              onChange={(e) => setHospital(hospitals.find((h) => h.id === e.target.value) ?? null)}
            >
              {hospitals.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name_ar}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>الفترة</label>
            <select
              value={period?.id ?? ""}
              onChange={(e) => setPeriod(periods.find((p) => p.id === e.target.value) ?? null)}
            >
              {periods.length === 0 && <option value="">لا توجد فترات</option>}
              {periods.map((p) => (
                <option key={p.id} value={p.id}>
                  {periodLabel(p)} — {STATUS_LABEL[p.status]}
                </option>
              ))}
            </select>
          </div>
          {period && (
            <div className="field">
              <label>الحالة</label>
              <div>
                <span className={STATUS_CLASS[period.status]}>{STATUS_LABEL[period.status]}</span>
              </div>
            </div>
          )}
          {canEnter && hospital && (
            <form className="row" style={{ gap: 8, alignItems: "flex-end" }} onSubmit={createPeriod}>
              <div className="field">
                <label>سنة جديدة</label>
                <input
                  type="number"
                  value={newYear}
                  min={2000}
                  max={2100}
                  onChange={(e) => setNewYear(Number(e.target.value))}
                  style={{ width: 90 }}
                />
              </div>
              <div className="field">
                <label>شهر</label>
                <select value={newMonth} onChange={(e) => setNewMonth(Number(e.target.value))}>
                  {AR_MONTHS.map((m, i) => (
                    <option key={m} value={i + 1}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <button className="primary" type="submit" disabled={busy}>
                إنشاء فترة
              </button>
            </form>
          )}
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      {notice && <div className="notice-box">{notice}</div>}
      {offline && (
        <div className="notice-box">
          وضع دون إنترنت: تُحفظ البيانات على هذا الجهاز وتُرسَل تلقائياً عند عودة الاتصال.
        </div>
      )}

      {period && (
        <div className="card">
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            {canSubmit && (period.status === "draft" || period.status === "returned") && (
              <button className="primary" disabled={busy} onClick={() => doAction("submit")}>
                إرسال للمراجعة
              </button>
            )}
            {canReview && period.status === "submitted" && (
              <button className="primary" disabled={busy} onClick={() => doAction("review")}>
                مراجعة
              </button>
            )}
            {canApprove && (period.status === "submitted" || period.status === "reviewed") && (
              <button className="primary" disabled={busy} onClick={() => doAction("approve")}>
                اعتماد
              </button>
            )}
            {canReview && period.status !== "returned" && period.status !== "draft" && (
              <button disabled={busy} onClick={() => doAction("return")}>
                إعادة للتعديل
              </button>
            )}
          </div>
          {!editable && (
            <p className="hint" style={{ marginBottom: 0 }}>
              هذه الفترة غير قابلة للتعديل في حالتها الحالية. أعدها إلى «مُعادة للتعديل» أولاً.
            </p>
          )}
        </div>
      )}

      {period && assigned.length === 0 && (
        <div className="card">
          <div className="empty">لا توجد مؤشرات مُسندة لهذا المستشفى بعد.</div>
        </div>
      )}

      {period &&
        sortedAssigned.map((a) => {
          const key = `${a.indicator.id}:${a.department_id ?? ""}`;
          const v = valuesByKey.get(key);
          const d = drafts[key] ?? { numerator: "", denominator: "", entered: "" };
          const isDirect = ["count", "sum", "entered"].includes(a.indicator.computation);
          return (
            <div className="card" key={a.assignment_id}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                <h3 style={{ margin: 0 }}>
                  {a.indicator.name_ar} <span className="hint">{a.indicator.code}</span>
                </h3>
                <div className="row" style={{ gap: 6 }}>
                  <span className="chip">
                    {a.department_id ? `قسم: ${deptName.get(a.department_id) ?? "—"}` : "على مستوى المستشفى"}
                  </span>
                  {v?.assessment && (
                    <span
                      className={`badge ${
                        v.assessment.status === "good"
                          ? "on"
                          : v.assessment.status === "poor"
                            ? "off"
                            : v.assessment.status === "warning"
                              ? "warn"
                              : ""
                      }`}
                    >
                      {v.assessment.label_ar}
                    </span>
                  )}
                </div>
              </div>
              <p className="hint" style={{ marginTop: 4 }}>
                {a.indicator.calculation_ar ?? ""} — الهدف:{" "}
                {a.target_override ?? a.indicator.target_value ?? "غير محدد"}
                {a.indicator.unit_ar ? ` (${a.indicator.unit_ar})` : ""}
              </p>
              <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
                {isDirect ? (
                  <div className="field">
                    <label>القيمة</label>
                    <input
                      type="number"
                      step="any"
                      disabled={!editable || !canEnter}
                      value={d.entered}
                      onChange={(e) => setDraft(key, { entered: e.target.value })}
                    />
                  </div>
                ) : (
                  <>
                    <div className="field">
                      <label>{a.indicator.numerator_label_ar ?? "البسط"}</label>
                      <input
                        type="number"
                        step="any"
                        disabled={!editable || !canEnter}
                        value={d.numerator}
                        onChange={(e) => setDraft(key, { numerator: e.target.value })}
                      />
                    </div>
                    <div className="field">
                      <label>{a.indicator.denominator_label_ar ?? "المقام"}</label>
                      <input
                        type="number"
                        step="any"
                        disabled={!editable || !canEnter}
                        value={d.denominator}
                        onChange={(e) => setDraft(key, { denominator: e.target.value })}
                      />
                    </div>
                  </>
                )}
                <div className="field">
                  <label>القيمة المحسوبة</label>
                  <div className="computed">{v?.value != null ? v.value : "—"}</div>
                </div>
                {editable && canEnter && (
                  <button className="primary" disabled={busy} onClick={() => saveValue(a)}>
                    حفظ
                  </button>
                )}
              </div>
            </div>
          );
        })}
    </div>
  );
}
