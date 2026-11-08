import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";
import PeriodFilter, { currentPeriod } from "../components/PeriodFilter";
import { Card, ErrorBox, Loading, Stat } from "../components/ui";
import { formatPercent, statusLabel } from "../reports";
import type { LateResponse, NationalOverview } from "../types";

export default function Tracking() {
  const [period, setPeriod] = useState(currentPeriod());
  const [onlyLate, setOnlyLate] = useState(false);

  const loadOverview = useCallback(
    () => api.reportOverview(period.year, period.month),
    [period.year, period.month],
  );
  const loadLate = useCallback(() => api.reportLate(period.year, period.month), [period.year, period.month]);

  const overview = useAsync<NationalOverview>(loadOverview, [period.year, period.month]);
  const late = useAsync<LateResponse>(loadLate, [period.year, period.month]);

  const lateIds = useMemo(
    () => new Set((late.data?.hospitals ?? []).map((h) => h.hospital_id)),
    [late.data],
  );

  const rows = useMemo(() => {
    const list = overview.data?.hospitals ?? [];
    return onlyLate ? list.filter((h) => lateIds.has(h.hospital_id) || !h.reported) : list;
  }, [overview.data, lateIds, onlyLate]);

  const total = overview.data?.hospitals_total ?? 0;
  const reported = overview.data?.hospitals_reported ?? 0;
  const lateCount = late.data?.hospitals.length ?? 0;

  return (
    <div>
      <PeriodFilter value={period} onChange={setPeriod} />

      {overview.error ? <ErrorBox message={overview.error} /> : null}
      {late.error ? <ErrorBox message={late.error} /> : null}
      {overview.loading && !overview.data ? <Loading what="حالة التقارير" /> : null}

      {overview.data ? (
        <>
          <div className="stat-grid">
            <Stat label="إجمالي المستشفيات" value={total} />
            <Stat label="أرسلت بياناتها" value={reported} />
            <Stat label="نسبة الإرسال" value={formatPercent(total ? (reported / total) * 100 : null)} />
            <Stat label="متأخرة عن الإرسال" value={lateCount} />
          </div>

          <div className="toolbar">
            <label style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ink)" }}>
              <input
                type="checkbox"
                checked={onlyLate}
                onChange={(e) => setOnlyLate(e.target.checked)}
                style={{ width: "auto" }}
              />
              إظهار المتأخرة فقط
            </label>
          </div>

          <Card title={`حالة التقارير الشهرية (${rows.length})`}>
            {rows.length === 0 ? (
              <div className="empty">لا توجد بيانات.</div>
            ) : (
              <div className="scroll-y">
                <table>
                  <thead>
                    <tr>
                      <th>المستشفى</th>
                      <th>المحافظة</th>
                      <th>الحالة</th>
                      <th>آخر تحديث</th>
                      <th>مؤشرات محسوبة</th>
                      <th>التحقيق</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((h) => {
                      const isLate = lateIds.has(h.hospital_id) || !h.reported;
                      return (
                        <tr key={h.hospital_id}>
                          <td>{h.hospital_name_ar}</td>
                          <td>{h.governorate_name_ar ?? "—"}</td>
                          <td>
                            {isLate ? (
                              <span className="badge bad">متأخر</span>
                            ) : (
                              <span className="badge on">{statusLabel(h.period_status)}</span>
                            )}
                          </td>
                          <td>{h.last_sync_label || "—"}</td>
                          <td>{h.indicators_with_value}</td>
                          <td>{formatPercent(h.compliance_percent)}</td>
                          <td>
                            <Link to={`/hospital/${h.hospital_id}?year=${period.year}&month=${period.month ?? ""}`} className="badge">
                              تفاصيل
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <div className="row">
            <button onClick={() => api.downloadReport("xlsx", period.year, period.month)}>تصدير Excel</button>
            <button onClick={() => api.downloadReport("pdf", period.year, period.month)}>تصدير PDF</button>
          </div>
        </>
      ) : null}
    </div>
  );
}
