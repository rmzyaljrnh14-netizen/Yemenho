// Smart assistant page for the desktop app (v0.8).
//
// The analysis runs on the backend over the rows the signed-in user may see.
// It only ever reports what is in the data: trends, anomalies, late submission,
// quality pressure and improvement areas, each with the numbers behind it.
// Nothing here invents a figure or a medical cause.

import { useCallback, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../useAsync";
import type { DraftReport, HospitalInsight, Insight } from "../types";

const SEVERITY_AR: Record<string, string> = { high: "عالية", medium: "متوسطة", info: "معلومة" };
const SEVERITY_CLASS: Record<string, string> = { high: "badge bad", medium: "badge warn", info: "badge" };
const KIND_AR: Record<string, string> = {
  trend: "اتجاه",
  anomaly: "قيمة غير معتادة",
  late_submission: "تأخر إرسال",
  low_compliance: "تدنّي تحقيق الأهداف",
  overdue_capa: "إجراءات متأخرة",
  high_risk: "مخاطر عالية",
  open_incidents: "حوادث مفتوحة",
  open_rca: "تحليل أسباب جذري",
};

const MONTHS_AR = [
  "", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
  "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
];

export default function Assistant() {
  const { me } = useAuth();
  const hospitalId = me?.scope_org.hospital_id ?? null;

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState<number | null>(null);

  const load = useCallback(
    () =>
      hospitalId
        ? api.assistantHospital(hospitalId, year, month)
        : Promise.resolve<HospitalInsight | null>(null),
    [hospitalId, year, month],
  );
  const bundle = useAsync<HospitalInsight | null>(load, [hospitalId, year, month]);
  const data = bundle.data;

  const years: number[] = [];
  for (let y = now.getFullYear() - 4; y <= now.getFullYear() + 1; y += 1) years.push(y);

  const insights = data?.insights ?? [];
  const counts = {
    high: insights.filter((i) => i.severity === "high").length,
    medium: insights.filter((i) => i.severity === "medium").length,
  };

  return (
    <div>
      <div className="notice-box">
        المساعد الذكي يبني نتائجه على البيانات المسجّلة فقط: اتجاهات المؤشرات، القيم غير المعتادة إحصائياً، تأخر
        الإرسال، ضغط الجودة وسلامة المرضى، ومجالات التحسين. كل نتيجة مرفقة بالأرقام التي حُسبت منها. لا يختلق
        النظام أي رقم أو سبب، وهذا تحليل آلي مساعد وليس حكماً طبياً أو إدارياً.
      </div>

      <div className="card">
        <div className="row">
          <div className="field">
            <label>السنة</label>
            <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>الشهر</label>
            <select
              value={month ?? ""}
              onChange={(e) => setMonth(e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">كل السنة</option>
              {MONTHS_AR.slice(1).map((name, i) => (
                <option key={name} value={i + 1}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {!hospitalId ? (
        <div className="card">
          <div className="empty">لا يرتبط حسابك بمستشفى، فلا تتوفر نتائج تحليلية.</div>
        </div>
      ) : null}

      {bundle.loading && !data ? <div className="card"><div className="empty">جارٍ تحليل البيانات...</div></div> : null}
      {bundle.error ? (
        <div className="card">
          <div className="error-box">
            تعذّر جلب التحليل من الخادم المركزي. يحتاج المساعد الذكي إلى اتصال بالشبكة، ويمكنك
            متابعة الإدخال والعمل محلياً ثم إعادة المحاولة عند عودة الاتصال.
          </div>
        </div>
      ) : null}

      {data ? (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-label">المستشفى</div>
              <div className="stat-value" style={{ fontSize: 18 }}>{data.hospital_name_ar}</div>
            </div>
            <div className="stat">
              <div className="stat-label">نسبة تحقيق الأهداف</div>
              <div className="stat-value">
                {data.compliance_percent === null ? "—" : `${data.compliance_percent.toFixed(1)}%`}
              </div>
            </div>
            <div className="stat">
              <div className="stat-label">مؤشرات محققة</div>
              <div className="stat-value">{data.indicators_met}</div>
              <div className="stat-sub">من {data.indicators_with_value} قيمة مسجّلة</div>
            </div>
            <div className="stat">
              <div className="stat-label">نقاط عالية الخطورة</div>
              <div className="stat-value">{counts.high}</div>
              <div className="stat-sub">متوسطة: {counts.medium}</div>
            </div>
          </div>

          {data.narrative_ar ? (
            <div className="card">
              <h3>صياغة مقترحة (مبنية على النتائج المحسوبة)</h3>
              <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.9 }}>{data.narrative_ar}</p>
            </div>
          ) : null}

          <div className="card">
            <h3>النتائج التحليلية</h3>
            {insights.length === 0 ? (
              <div className="empty">لا توجد نتائج تحليلية لهذه الفترة — قد لا تكفي البيانات المسجّلة.</div>
            ) : (
              <div style={{ display: "grid", gap: 10, marginTop: 8 }}>
                {insights.map((ins, idx) => (
                  <InsightRow key={idx} insight={ins} />
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <h3>مجالات مقترحة للتحسين (مؤشرات دون الهدف)</h3>
            {data.improvement_areas.length === 0 ? (
              <div className="empty">لا توجد مؤشرات دون الهدف في البيانات الحالية.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>المؤشر</th>
                    <th>القسم</th>
                    <th>القيمة</th>
                    <th>المستهدف</th>
                    <th>التقييم</th>
                  </tr>
                </thead>
                <tbody>
                  {data.improvement_areas.map((a) => (
                    <tr key={`${a.indicator_code}-${a.department_name_ar ?? ""}`}>
                      <td>
                        {a.indicator_name_ar} <span style={{ color: "#64748b" }}>[{a.indicator_code}]</span>
                      </td>
                      <td>{a.department_name_ar ?? "على مستوى المستشفى"}</td>
                      <td>
                        {a.value ?? "—"} {a.unit_ar ?? ""}
                      </td>
                      <td>{a.target_value ?? "—"}</td>
                      <td>
                        <span className={a.assessment_status === "poor" ? "badge bad" : "badge warn"}>
                          {a.assessment_label_ar}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <DraftReportCard hospitalId={hospitalId} year={year} month={month} />

          <div className="notice-box" style={{ marginTop: 12 }}>
            {data.disclaimer_ar}
            <div style={{ marginTop: 6, color: "#64748b", fontSize: 12 }}>
              تاريخ التوليد: {data.generated_at}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function InsightRow({ insight }: { insight: Insight }) {
  const [open, setOpen] = useState(false);
  const hasBasis = Object.keys(insight.basis ?? {}).length > 0;
  return (
    <div className="card" style={{ padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
        <div>
          <span className={SEVERITY_CLASS[insight.severity] ?? "badge"}>
            {SEVERITY_AR[insight.severity] ?? insight.severity}
          </span>{" "}
          <span className="badge">{KIND_AR[insight.kind] ?? insight.kind}</span>{" "}
          <strong style={{ marginInlineStart: 6 }}>{insight.title_ar}</strong>
        </div>
        {hasBasis ? (
          <button onClick={() => setOpen((o) => !o)}>{open ? "إخفاء الأساس" : "عرض الأساس"}</button>
        ) : null}
      </div>
      <div style={{ marginTop: 6, lineHeight: 1.8 }}>{insight.detail_ar}</div>
      {open && hasBasis ? (
        <pre
          dir="ltr"
          style={{
            marginTop: 8,
            background: "#f8fafc",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            padding: 10,
            fontSize: 12,
            overflowX: "auto",
          }}
        >
          {JSON.stringify(insight.basis, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

function DraftReportCard({
  hospitalId,
  year,
  month,
}: {
  hospitalId: string | null;
  year: number;
  month: number | null;
}) {
  const [report, setReport] = useState<DraftReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    if (!hospitalId) return;
    setLoading(true);
    setError(null);
    try {
      setReport(await api.assistantDraftReport(hospitalId, year, month));
    } catch {
      setError("تعذّر توليد المسودة.");
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    if (report) {
      try {
        await navigator.clipboard.writeText(report.report_text_ar);
      } catch {
        /* clipboard may be blocked; the text is visible anyway */
      }
    }
  };

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <h3 style={{ margin: 0 }}>مسودة تقرير إداري</h3>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="primary" onClick={generate} disabled={loading || !hospitalId}>
            {loading ? "جارٍ التوليد..." : "توليد المسودة"}
          </button>
          {report ? <button onClick={copy}>نسخ</button> : null}
        </div>
      </div>
      <div style={{ marginTop: 12 }}>
        {error ? <div className="error-box">{error}</div> : null}
        {report ? (
          <pre
            dir="rtl"
            style={{
              whiteSpace: "pre-wrap",
              lineHeight: 1.9,
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              padding: 12,
              fontFamily: "inherit",
            }}
          >
            {report.report_text_ar}
          </pre>
        ) : (
          <div className="empty">اضغط «توليد المسودة» لبناء مسودة مبنية على الأرقام المسجّلة لهذه الفترة.</div>
        )}
      </div>
    </div>
  );
}
