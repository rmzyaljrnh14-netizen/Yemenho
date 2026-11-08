import { useCallback, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";
import PeriodFilter, { currentPeriod } from "../components/PeriodFilter";
import Chart from "../components/Chart";
import { Card, ComplianceBar, ErrorBox, Loading, Stat } from "../components/ui";
import { assessmentBadgeClass, formatNumber, formatPercent, movementArrow, movementLabel, statusLabel } from "../reports";
import type { HospitalReport } from "../types";

export default function HospitalDetail() {
  const { hospitalId = "" } = useParams();
  const [params] = useSearchParams();
  const initial: { year: number; month: number | null } = {
    year: Number(params.get("year")) || currentPeriod().year,
    month: params.get("month") ? Number(params.get("month")) : currentPeriod().month,
  };
  const [period, setPeriod] = useState(initial);

  const load = useCallback(
    () => api.reportHospital(hospitalId, period.year, period.month),
    [hospitalId, period.year, period.month],
  );
  const { data, loading, error } = useAsync<HospitalReport>(load, [hospitalId, period.year, period.month]);

  return (
    <div>
      <PeriodFilter value={period} onChange={setPeriod} />
      {error ? <ErrorBox message={error} /> : null}
      {loading && !data ? <Loading what="تقرير المستشفى" /> : null}

      {data ? (
        <>
          <Card
            title={data.hospital_name_ar}
            actions={<span className="badge">{statusLabel(data.period_status)}</span>}
          >
            <div className="stat-grid" style={{ marginBottom: 0 }}>
              <Stat label="نسبة تحقيق الأهداف" value={formatPercent(data.compliance_percent)} />
              <Stat label="مؤشرات محققة" value={data.indicators_met} />
              <Stat label="دون الهدف" value={data.indicators_at_risk} />
              <Stat label="غير محسوبة" value={data.indicators_unknown} />
              <Stat label="محسوبة / الإجمالي" value={`${data.indicators_with_value} / ${data.indicators_total}`} />
            </div>
            <div style={{ marginTop: 12 }}>
              <ComplianceBar percent={data.compliance_percent} />
            </div>
          </Card>

          <Card title="مؤشرات المستشفى في هذه الفترة">
            {data.points.length === 0 ? (
              <div className="empty">لا توجد مؤشرات مسندة أو قيم مسجّلة.</div>
            ) : (
              <div className="scroll-y">
                <table>
                  <thead>
                    <tr>
                      <th>الرمز</th>
                      <th>المؤشر</th>
                      <th>القسم</th>
                      <th>القيمة</th>
                      <th>الهدف</th>
                      <th>التقييم</th>
                      <th>الاتجاه</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.points.map((p, i) => (
                      <tr key={`${p.indicator_id}-${p.department_id ?? "h"}-${i}`}>
                        <td>{p.code}</td>
                        <td>{p.name_ar}</td>
                        <td>{p.department_name_ar ?? "على مستوى المستشفى"}</td>
                        <td>
                          {formatNumber(p.value)}
                          {p.unit_ar ? ` ${p.unit_ar}` : ""}
                        </td>
                        <td>{formatNumber(p.target_value)}</td>
                        <td>
                          <span className={assessmentBadgeClass(p.assessment_status)}>{p.assessment_label_ar}</span>
                        </td>
                        <td>
                          {movementArrow(p.movement)} {movementLabel(p.movement, p.improving)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <TrendCard hospitalId={hospitalId} points={data.points} year={period.year} month={period.month} />
        </>
      ) : null}
    </div>
  );
}

function TrendCard({
  hospitalId,
  points,
  year,
  month,
}: {
  hospitalId: string;
  points: HospitalReport["points"];
  year: number;
  month: number | null;
}) {
  const withValues = points.filter((p) => p.value !== null);
  const [indicatorId, setIndicatorId] = useState<string>(withValues[0]?.indicator_id ?? "");

  const load = useCallback(
    () => api.reportTrend(indicatorId, hospitalId, 12),
    [indicatorId, hospitalId],
  );
  const { data, loading, error } = useAsync(load, [indicatorId, hospitalId, year, month]);

  if (withValues.length === 0) return null;

  const option = {
    tooltip: { trigger: "axis" },
    grid: { left: 60, right: 30, top: 20, bottom: 40 },
    xAxis: { type: "category", data: (data?.points ?? []).map((p) => p.period_label) },
    yAxis: { type: "value" },
    series: [
      {
        type: "line",
        smooth: true,
        data: (data?.points ?? []).map((p) => p.value),
        connectNulls: true,
      },
    ],
  };

  return (
    <Card title="الاتجاه الزمني للمؤشر">
      <div className="toolbar">
        <div className="field" style={{ minWidth: 320 }}>
          <label>المؤشر</label>
          <select value={indicatorId} onChange={(e) => setIndicatorId(e.target.value)}>
            {withValues.map((p, i) => (
              <option key={`${p.indicator_id}-${i}`} value={p.indicator_id}>
                {p.code} — {p.name_ar}
                {p.department_name_ar ? ` (${p.department_name_ar})` : ""}
              </option>
            ))}
          </select>
        </div>
      </div>
      {error ? <ErrorBox message={error} /> : null}
      {loading && !data ? <Loading what="الاتجاه" /> : null}
      {data ? <Chart option={option} height={320} /> : null}
    </Card>
  );
}
