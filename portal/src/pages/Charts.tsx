import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";
import PeriodFilter, { currentPeriod } from "../components/PeriodFilter";
import Chart from "../components/Chart";
import { Card, ErrorBox, Loading } from "../components/ui";
import { complianceColor, formatPercent } from "../reports";
import type { NationalOverview } from "../types";

export default function Charts() {
  const [period, setPeriod] = useState(currentPeriod());
  const load = useCallback(() => api.reportOverview(period.year, period.month), [period.year, period.month]);
  const { data, loading, error } = useAsync<NationalOverview>(load, [period.year, period.month]);

  const govOption = useMemo(() => {
    const rows = [...(data?.governorates ?? [])].sort(
      (a, b) => (a.compliance_percent ?? -1) - (b.compliance_percent ?? -1),
    );
    return {
      grid: { left: 120, right: 40, top: 20, bottom: 30 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
      yAxis: { type: "category", data: rows.map((g) => g.governorate_name_ar) },
      series: [
        {
          type: "bar",
          data: rows.map((g) => ({
            value: g.compliance_percent ?? 0,
            itemStyle: { color: complianceColor(g.compliance_percent) },
          })),
          label: { show: true, position: "insideLeft", formatter: (p: { value: number }) => `${p.value.toFixed(1)}%` },
        },
      ],
    };
  }, [data]);

  const reportedOption = useMemo(() => {
    const total = data?.hospitals_total ?? 0;
    const reported = data?.hospitals_reported ?? 0;
    return {
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          data: [
            { name: "أرسلت بياناتها", value: reported, itemStyle: { color: "#15803d" } },
            { name: "لم تُرسل بعد", value: Math.max(0, total - reported), itemStyle: { color: "#cbd5e1" } },
          ],
          label: { formatter: "{b}: {c}" },
        },
      ],
    };
  }, [data]);

  const assessmentOption = useMemo(() => {
    const met = data?.indicators_met ?? 0;
    const atRisk = data?.indicators_at_risk ?? 0;
    const withValue = data?.indicators_with_value ?? 0;
    const unknown = Math.max(0, (data?.indicators_total ?? 0) - withValue);
    return {
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          type: "pie",
          radius: "65%",
          data: [
            { name: "محقق للهدف", value: met, itemStyle: { color: "#15803d" } },
            { name: "دون الهدف", value: atRisk, itemStyle: { color: "#b45309" } },
            { name: "غير محسوب", value: unknown, itemStyle: { color: "#94a3b8" } },
          ],
          label: { formatter: "{b}: {c}" },
        },
      ],
    };
  }, [data]);

  return (
    <div>
      <PeriodFilter value={period} onChange={setPeriod} />
      {error ? <ErrorBox message={error} /> : null}
      {loading && !data ? <Loading what="الرسوم البيانية" /> : null}

      {data ? (
        <div className="grid-2">
          <Card title="نسبة تحقيق الأهداف حسب المحافظة">
            {data.governorates.length === 0 ? (
              <div className="empty">لا بيانات.</div>
            ) : (
              <Chart option={govOption} height={Math.max(240, data.governorates.length * 42)} />
            )}
          </Card>
          <Card title={`التغطية: نسبة المستشفيات المبلِّغة — ${formatPercent(data.hospitals_total ? (data.hospitals_reported / data.hospitals_total) * 100 : null)}`}>
            <Chart option={reportedOption} height={300} />
          </Card>
          <Card title="توزيع تقييم المؤشرات وطنياً">
            <Chart option={assessmentOption} height={300} />
          </Card>
          <Card title="ملخص">
            <dl className="kv">
              <dt>السنة</dt>
              <dd>{data.year}</dd>
              <dt>مؤشرات محسوبة</dt>
              <dd>
                {data.indicators_with_value} من {data.indicators_total}
              </dd>
              <dt>نسبة تحقيق الأهداف</dt>
              <dd>{formatPercent(data.compliance_percent)}</dd>
              <dt>متوسط تحقيق المستشفيات</dt>
              <dd>{formatPercent(data.average_hospital_compliance)}</dd>
            </dl>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
