import { useCallback, useState } from "react";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";
import { useAuth } from "../auth";
import PeriodFilter, { currentPeriod } from "../components/PeriodFilter";
import { Card, Empty, ErrorBox, Loading, Stat } from "../components/ui";
import { formatPercent } from "../reports";
import type { DraftReport, HospitalInsight, Hospital, Insight, NationalInsight } from "../types";

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

export default function Assistant() {
  const { me } = useAuth();
  const [period, setPeriod] = useState(currentPeriod());
  const [mode, setMode] = useState<"national" | "hospital">("national");
  const [pickedHospital, setPickedHospital] = useState<string>("");

  const scopedHospital = me?.scope_org.hospital_id ?? null;
  const isCentral = scopedHospital === null;
  const hospitalId = scopedHospital ?? pickedHospital;

  const loadHospitals = useCallback(() => api.hospitals(), []);
  const hospitals = useAsync<Hospital[]>(loadHospitals, []);
  const loadStatus = useCallback(() => api.assistantStatus(), []);
  const status = useAsync(loadStatus, []);

  // The hospital picker must show as soon as the person picks "hospital scope",
  // even before a hospital is chosen (otherwise there is nothing to choose from).
  const wantHospital = mode === "hospital";
  const useNational = !wantHospital || !hospitalId;

  const loadNational = useCallback(
    () => api.assistantNational(period.year, period.month),
    [period.year, period.month],
  );
  const loadHospital = useCallback(
    () => (hospitalId ? api.assistantHospital(hospitalId, period.year, period.month) : Promise.resolve(null)),
    [hospitalId, period.year, period.month],
  );

  const national = useAsync<NationalInsight>(loadNational, [
    period.year,
    period.month,
    useNational ? "n" : "h",
  ]);
  const hospital = useAsync<HospitalInsight | null>(loadHospital, [
    hospitalId,
    period.year,
    period.month,
    useNational ? "n" : "h",
  ]);

  const active = useNational ? national : hospital;
  const insights: Insight[] = active.data?.insights ?? [];
  const counts = {
    high: insights.filter((i) => i.severity === "high").length,
    medium: insights.filter((i) => i.severity === "medium").length,
    info: insights.filter((i) => i.severity === "info").length,
  };

  return (
    <div>
      <div className="notice-box">
        المساعد الذكي يبني نتائجه على البيانات المسجّلة فقط: اتجاهات المؤشرات، القيم غير المعتادة إحصائياً، تأخر
        الإرسال، ضغط الجودة وسلامة المرضى، ومجالات التحسين. كل نتيجة مرفقة بالأرقام التي حُسبت منها. لا يختلق
        النظام أي رقم أو سبب، وهذا تحليل آلي مساعد وليس حكماً طبياً أو إدارياً.
      </div>

      {status.data ? (
        <div className="notice-box" style={{ background: "#f1f5f9", borderColor: "#cbd5e1" }}>
          {status.data.note_ar}
        </div>
      ) : null}

      <div className="toolbar">
        <div className="field">
          <label>نطاق التحليل</label>
          <select
            value={useNational ? "national" : "hospital"}
            onChange={(e) => setMode(e.target.value as "national" | "hospital")}
          >
            <option value="national">وطني (كل المستشفيات المتاحة)</option>
            <option value="hospital">مستشفى واحد</option>
          </select>
        </div>
        {wantHospital && isCentral ? (
          <div className="field">
            <label>المستشفى</label>
            <select value={pickedHospital} onChange={(e) => setPickedHospital(e.target.value)}>
              <option value="">اختر مستشفى</option>
              {(hospitals.data ?? []).map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name_ar}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>

      <PeriodFilter value={period} onChange={setPeriod} allowAll />

      {active.loading && !active.data ? <Loading what="تحليل البيانات" /> : null}
      {active.error ? <ErrorBox message={active.error} /> : null}

      {active.data ? (
        <>
          <div className="stat-grid">
            {useNational ? (
              <>
                <Stat
                  label="إجمالي المستشفيات"
                  value={(active.data as NationalInsight).hospitals_total}
                  sub={`أرسلت بياناتها: ${(active.data as NationalInsight).hospitals_reported}`}
                />
                <Stat
                  label="نسبة تحقيق الأهداف وطنياً"
                  value={formatPercent((active.data as NationalInsight).compliance_percent)}
                />
              </>
            ) : (
              <>
                <Stat label="المستشفى" value={(active.data as HospitalInsight).hospital_name_ar} />
                <Stat
                  label="نسبة تحقيق الأهداف"
                  value={formatPercent((active.data as HospitalInsight).compliance_percent)}
                />
                <Stat
                  label="مؤشرات محققة"
                  value={(active.data as HospitalInsight).indicators_met}
                  sub={`من ${(active.data as HospitalInsight).indicators_with_value} قيمة مسجّلة`}
                />
              </>
            )}
            <Stat label="نقاط عالية الخطورة" value={counts.high} />
            <Stat label="نقاط متوسطة" value={counts.medium} />
          </div>

          {active.data.narrative_ar ? (
            <Card title="صياغة مقترحة (مبنية على النتائج المحسوبة)">
              <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.9 }}>{active.data.narrative_ar}</p>
            </Card>
          ) : null}

          <Card title="النتائج التحليلية">
            {insights.length === 0 ? (
              <Empty message="لا توجد نتائج تحليلية لهذه الفترة — قد لا تكفي البيانات المسجّلة." />
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                {insights.map((ins, idx) => (
                  <InsightRow key={idx} insight={ins} />
                ))}
              </div>
            )}
          </Card>

          {!useNational ? <ImprovementAreas bundle={active.data as HospitalInsight} /> : null}
          {!useNational ? (
            <DraftReportCard hospitalId={hospitalId} year={period.year} month={period.month} />
          ) : null}

          <div className="notice-box" style={{ marginTop: 12 }}>
            {active.data.disclaimer_ar}
            <div style={{ marginTop: 6, color: "#64748b", fontSize: 12 }}>
              تاريخ التوليد: {active.data.generated_at}
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
          <button onClick={() => setOpen((o) => !o)}>
            {open ? "إخفاء الأساس" : "عرض الأساس"}
          </button>
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

function ImprovementAreas({ bundle }: { bundle: HospitalInsight }) {
  const areas = bundle.improvement_areas ?? [];
  return (
    <Card title="مجالات مقترحة للتحسين (مؤشرات دون الهدف)">
      {areas.length === 0 ? (
        <Empty message="لا توجد مؤشرات دون الهدف في البيانات الحالية." />
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
            {areas.map((a) => (
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
    </Card>
  );
}

function DraftReportCard({ hospitalId, year, month }: { hospitalId: string; year: number; month: number | null }) {
  const [report, setReport] = useState<DraftReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
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
    <Card
      title="مسودة تقرير إداري"
      actions={
        <div style={{ display: "flex", gap: 8 }}>
          <button className="primary" onClick={generate} disabled={loading}>
            {loading ? "جارٍ التوليد..." : "توليد المسودة"}
          </button>
          {report ? (
            <button onClick={copy}>
              نسخ
            </button>
          ) : null}
        </div>
      }
    >
      {error ? <ErrorBox message={error} /> : null}
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
        <Empty message="اضغط «توليد المسودة» لبناء مسودة مبنية على الأرقام المسجّلة لهذه الفترة." />
      )}
    </Card>
  );
}
