import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import Chart from "../components/Chart";
import {
  complianceColor,
  currentMonth,
  currentYear,
  formatNumber,
  formatPercent,
  MONTHS_AR,
  statusLabel,
} from "../reports";
import type {
  CompareResponse,
  Hospital,
  HospitalReport,
  LateResponse,
  NationalOverview,
  TrendResponse,
} from "../types";

export default function Reports() {
  const { me } = useAuth();
  const isCentral = me?.scope_org.level === "central";
  const isGovernorate = me?.scope_org.level === "governorate";
  const canSeeAll = isCentral || isGovernorate;

  const [year, setYear] = useState(currentYear());
  const [month, setMonth] = useState<number | null>(currentMonth());
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [overview, setOverview] = useState<NationalOverview | null>(null);
  const [compare, setCompare] = useState<CompareResponse | null>(null);
  const [late, setLate] = useState<LateResponse | null>(null);
  const [selectedHospital, setSelectedHospital] = useState<string>("");
  const [hospitalReport, setHospitalReport] = useState<HospitalReport | null>(null);
  const [selectedIndicator, setSelectedIndicator] = useState<string>("");
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const list = await api.hospitals();
        setHospitals(list);
        if (list.length > 0) setSelectedHospital(list[0].id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل المستشفيات.");
      }
    })();
  }, []);

  useEffect(() => {
    if (!canSeeAll) return;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [ov, cmp, lt] = await Promise.all([
          api.reportOverview(year, month),
          api.reportCompare(year, month),
          api.reportLate(year, month),
        ]);
        setOverview(ov);
        setCompare(cmp);
        setLate(lt);
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل التقارير.");
      } finally {
        setLoading(false);
      }
    })();
  }, [year, month, canSeeAll]);

  useEffect(() => {
    if (!selectedHospital) return;
    (async () => {
      try {
        setError(null);
        const rep = await api.reportHospital(selectedHospital, year, month);
        setHospitalReport(rep);
        const first = rep.points.find((p) => p.value !== null) ?? rep.points[0];
        setSelectedIndicator(first ? first.indicator_id : "");
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل تقرير المستشفى.");
      }
    })();
  }, [selectedHospital, year, month]);

  useEffect(() => {
    if (!selectedHospital || !selectedIndicator) {
      setTrend(null);
      return;
    }
    (async () => {
      try {
        setTrend(await api.reportTrend(selectedIndicator, selectedHospital, 12));
      } catch {
        setTrend(null);
      }
    })();
  }, [selectedIndicator, selectedHospital]);

  const trendOption = useMemo(() => {
    const labels = trend?.points.map((p) => p.period_label) ?? [];
    const values = trend?.points.map((p) => p.value) ?? [];
    const target = hospitalReport?.points.find((p) => p.indicator_id === selectedIndicator)?.target_value ?? null;
    return {
      grid: { left: 60, right: 20, top: 40, bottom: 40 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: labels },
      yAxis: { type: "value" },
      series: [
        {
          name: "القيمة",
          type: "line",
          data: values,
          smooth: true,
          connectNulls: false,
          itemStyle: { color: "#0f766e" },
          areaStyle: { opacity: 0.08 },
          markLine:
            target !== null
              ? {
                  silent: true,
                  symbol: "none",
                  data: [{ yAxis: target, name: "الهدف" }],
                  lineStyle: { color: "#b45309", type: "dashed" },
                  label: { formatter: "الهدف", position: "insideEndTop" },
                }
              : undefined,
        },
      ],
    };
  }, [trend, hospitalReport, selectedIndicator]);

  const compareOption = useMemo(() => {
    const rows = compare?.hospitals ?? [];
    return {
      grid: { left: 160, right: 40, top: 20, bottom: 40 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
      yAxis: {
        type: "category",
        data: rows.map((r) => r.hospital_name_ar).reverse(),
        axisLabel: { width: 150, overflow: "truncate" },
      },
      series: [
        {
          name: "نسبة تحقيق الأهداف",
          type: "bar",
          data: rows
            .map((r) => ({
              value: r.compliance_percent ?? 0,
              itemStyle: { color: complianceColor(r.compliance_percent) },
            }))
            .reverse(),
          label: {
            show: true,
            position: "right",
            formatter: (p: { value: number }) => (p.value ? `${p.value}%` : "لا بيانات"),
          },
        },
      ],
    };
  }, [compare]);

  const assessmentOption = useMemo(() => {
    const points = hospitalReport?.points ?? [];
    const counts = { good: 0, warning: 0, poor: 0, unknown: 0 };
    for (const p of points) counts[p.assessment_status] += 1;
    return {
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          data: [
            { value: counts.good, name: "محقق للهدف", itemStyle: { color: "#15803d" } },
            { value: counts.warning, name: "دون الهدف", itemStyle: { color: "#b45309" } },
            { value: counts.poor, name: "خارج الحدود", itemStyle: { color: "#b91c1c" } },
            { value: counts.unknown, name: "غير محسوب", itemStyle: { color: "#94a3b8" } },
          ].filter((d) => d.value > 0),
          label: { formatter: "{b}: {c}" },
        },
      ],
    };
  }, [hospitalReport]);

  async function download(format: "xlsx" | "pdf") {
    setNotice(null);
    setError(null);
    try {
      await api.downloadReport(format, year, month, canSeeAll ? undefined : selectedHospital || undefined);
      setNotice(`تم إنشاء ملف ${format === "pdf" ? "PDF" : "Excel"}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر إنشاء الملف.");
    }
  }

  return (
    <>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>التقارير ولوحات المعلومات</h3>
          <div className="row" style={{ gap: 8 }}>
            <label style={{ margin: 0 }}>
              السنة
              <input
                type="number"
                value={year}
                onChange={(e) => setYear(Number(e.target.value) || currentYear())}
                style={{ width: 110 }}
              />
            </label>
            <label style={{ margin: 0 }}>
              الشهر
              <select value={month ?? ""} onChange={(e) => setMonth(e.target.value ? Number(e.target.value) : null)}>
                <option value="">كل الأشهر</option>
                {MONTHS_AR.map((m, i) => (
                  <option key={m} value={i + 1}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary" onClick={() => download("xlsx")}>
              تصدير Excel
            </button>
            <button className="primary" onClick={() => download("pdf")}>
              تصدير PDF
            </button>
          </div>
        </div>
        <p className="hint" style={{ marginBottom: 0 }}>
          كل الأرقام محسوبة من البيانات الفعلية المُدخلة. المؤشرات التي لم تُدخَل تظهر «غير محسوب» ولا تُقدَّر.
        </p>
      </div>

      {notice && <div className="notice-box">{notice}</div>}
      {error && <div className="error-box">{error}</div>}

      {canSeeAll && overview && (
        <>
          <div className="stat-grid">
            <Stat label="المستشفيات" value={String(overview.hospitals_total)} />
            <Stat label="أرسلت بياناتها" value={`${overview.hospitals_reported} / ${overview.hospitals_total}`} />
            <Stat label="مؤشرات محسوبة" value={String(overview.indicators_with_value)} />
            <Stat label="مؤشرات محققة للهدف" value={String(overview.indicators_met)} />
            <Stat
              label="نسبة تحقيق الأهداف"
              value={formatPercent(overview.compliance_percent)}
              tone={complianceColor(overview.compliance_percent)}
            />
            <Stat label="مؤشرات دون الهدف" value={String(overview.indicators_at_risk)} />
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>مقارنة المستشفيات — نسبة تحقيق الأهداف</h3>
            {compare && compare.hospitals.length > 0 ? (
              <Chart option={compareOption} height={Math.max(200, compare.hospitals.length * 46)} />
            ) : (
              <div className="empty">لا توجد بيانات لهذه الفترة.</div>
            )}
          </div>

          <div className="grid-2">
            <div className="card">
              <h3 style={{ marginTop: 0 }}>الأداء حسب المحافظة</h3>
              {overview.governorates.length === 0 ? (
                <div className="empty">لا توجد محافظات ضمن نطاقك.</div>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>المحافظة</th>
                      <th>المستشفيات</th>
                      <th>أرسلت</th>
                      <th>نسبة التحقيق</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.governorates.map((g) => (
                      <tr key={g.governorate_name_ar}>
                        <td>{g.governorate_name_ar}</td>
                        <td>{g.hospitals}</td>
                        <td>{g.reported}</td>
                        <td style={{ color: complianceColor(g.compliance_percent), fontWeight: 700 }}>
                          {formatPercent(g.compliance_percent)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="card">
              <h3 style={{ marginTop: 0 }}>مستشفيات متأخرة عن الإرسال</h3>
              {late && late.hospitals.length === 0 ? (
                <div className="notice-box">لا يوجد تأخير — جميع المستشفيات أرسلت بياناتها.</div>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>المستشفى</th>
                      <th>المحافظة</th>
                      <th>الحالة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(late?.hospitals ?? []).map((h) => (
                      <tr key={h.hospital_id}>
                        <td>{h.hospital_name_ar}</td>
                        <td>{h.governorate_name_ar ?? "—"}</td>
                        <td>
                          <span className="badge warn">{h.status_label_ar}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>أداء المستشفيات</h3>
            <div className="scroll-y">
              <table>
                <thead>
                  <tr>
                    <th>المستشفى</th>
                    <th>المحافظة</th>
                    <th>الحالة</th>
                    <th>مؤشرات محسوبة</th>
                    <th>محققة</th>
                    <th>دون الهدف</th>
                    <th>نسبة التحقيق</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.hospitals.map((h) => (
                    <tr key={h.hospital_id}>
                      <td>{h.hospital_name_ar}</td>
                      <td>{h.governorate_name_ar ?? "—"}</td>
                      <td>
                        <span className={h.reported ? "badge ok" : "badge warn"}>
                          {h.reported ? statusLabel(h.period_status) : h.last_sync_label}
                        </span>
                      </td>
                      <td>{h.indicators_with_value}</td>
                      <td>{h.indicators_met}</td>
                      <td>{h.indicators_at_risk}</td>
                      <td style={{ color: complianceColor(h.compliance_percent), fontWeight: 700 }}>
                        {formatPercent(h.compliance_percent)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!canSeeAll && (
        <div className="notice-box">
          تعرض هذه الصفحة بيانات مستشفاك فقط. الإدارة المركزية ومكاتب الصحة ترى بيانات أكثر.
        </div>
      )}

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>تقرير مستشفى</h3>
          <label style={{ margin: 0, minWidth: 260 }}>
            المستشفى
            <select value={selectedHospital} onChange={(e) => setSelectedHospital(e.target.value)}>
              {hospitals.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name_ar}
                </option>
              ))}
            </select>
          </label>
        </div>

        {hospitalReport && (
          <>
            <div className="stat-grid" style={{ marginTop: 12 }}>
              <Stat label="حالة الفترة" value={statusLabel(hospitalReport.period_status)} />
              <Stat label="مؤشرات محسوبة" value={`${hospitalReport.indicators_with_value} / ${hospitalReport.indicators_total}`} />
              <Stat label="محققة للهدف" value={String(hospitalReport.indicators_met)} />
              <Stat
                label="نسبة تحقيق الأهداف"
                value={formatPercent(hospitalReport.compliance_percent)}
                tone={complianceColor(hospitalReport.compliance_percent)}
              />
            </div>

            {hospitalReport.points.length === 0 ? (
              <div className="empty">لا توجد بيانات لهذه الفترة.</div>
            ) : (
              <>
                <div className="grid-2">
                  <div>
                    <h4>اتجاه مؤشر خلال 12 شهراً</h4>
                    <label>
                      المؤشر
                      <select value={selectedIndicator} onChange={(e) => setSelectedIndicator(e.target.value)}>
                        {hospitalReport.points.map((p) => (
                          <option key={`${p.indicator_id}:${p.department_id ?? ""}`} value={p.indicator_id}>
                            {p.name_ar} {p.department_name_ar ? `— ${p.department_name_ar}` : ""}
                          </option>
                        ))}
                      </select>
                    </label>
                    {trend && trend.points.some((p) => p.value !== null) ? (
                      <Chart option={trendOption} height={280} />
                    ) : (
                      <div className="empty">لا توجد سلسلة زمنية كافية لهذا المؤشر بعد.</div>
                    )}
                  </div>
                  <div>
                    <h4>توزيع التقييم</h4>
                    <Chart option={assessmentOption} height={280} />
                  </div>
                </div>

                <h4>تفاصيل المؤشرات</h4>
                <div className="scroll-y">
                  <table>
                    <thead>
                      <tr>
                        <th>المؤشر</th>
                        <th>القسم</th>
                        <th>القيمة</th>
                        <th>الوحدة</th>
                        <th>الهدف</th>
                        <th>التقييم</th>
                        <th>الاتجاه</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hospitalReport.points.map((p) => (
                        <tr key={`${p.indicator_id}:${p.department_id ?? ""}`}>
                          <td>
                            {p.name_ar} <span className="hint">{p.code}</span>
                          </td>
                          <td>{p.department_name_ar ?? "المستشفى"}</td>
                          <td>{formatNumber(p.value)}</td>
                          <td>{p.unit_ar ?? "—"}</td>
                          <td>{formatNumber(p.target_value)}</td>
                          <td>
                            <span
                              className={
                                p.assessment_status === "good"
                                  ? "badge on"
                                  : p.assessment_status === "warning"
                                    ? "badge warn"
                                    : p.assessment_status === "poor"
                                      ? "badge off"
                                      : "badge"
                              }
                            >
                              {p.assessment_label_ar}
                            </span>
                          </td>
                          <td>{p.improving === null ? "—" : p.improving ? "تحسّن" : "تراجع"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="stat">
      <div className="hint">{label}</div>
      <div className="stat-value" style={tone ? { color: tone } : undefined}>
        {value}
      </div>
    </div>
  );
}
