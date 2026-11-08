import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAsync } from "../lib/useAsync";
import PeriodFilter, { currentPeriod } from "../components/PeriodFilter";
import { Card, ComplianceBar, ErrorBox, Loading, Stat } from "../components/ui";
import { formatNumber, formatPercent } from "../reports";
import type { NationalOverview } from "../types";

export default function Dashboard() {
  const { me } = useAuth();
  const [period, setPeriod] = useState(currentPeriod());

  const load = useCallback(
    () => api.reportOverview(period.year, period.month),
    [period.year, period.month],
  );
  const { data, loading, error } = useAsync<NationalOverview>(load, [period.year, period.month]);

  const level = me?.scope_org.level;
  const scopeNote =
    level === "central"
      ? "عرض وطني شامل لجميع المحافظات والمستشفيات."
      : level === "governorate"
        ? "عرض مقيّد بمستشفيات محافظتك فقط."
        : level === "hospital"
          ? "عرض مقيّد بمستشفاك فقط."
          : "عرض مقيّد بنطاقك.";

  return (
    <div>
      <div className="notice-box">{scopeNote}</div>

      <PeriodFilter value={period} onChange={setPeriod} />

      {error ? <ErrorBox message={error} /> : null}
      {loading && !data ? <Loading what="اللوحة الوطنية" /> : null}

      {data ? (
        <>
          <div className="stat-grid">
            <Stat
              label="المستشفيات المبلِّغة"
              value={`${data.hospitals_reported} / ${data.hospitals_total}`}
              sub={data.hospitals_total ? `${formatPercent((data.hospitals_reported / data.hospitals_total) * 100)} إرسال` : "لا مستشفيات"}
            />
            <Stat label="نسبة تحقيق الأهداف (وطني)" value={formatPercent(data.compliance_percent)} />
            <Stat label="متوسط تحقيق المستشفيات" value={formatPercent(data.average_hospital_compliance)} />
            <Stat label="مؤشرات محسوبة" value={`${data.indicators_with_value} / ${data.indicators_total}`} />
            <Stat label="مؤشرات محققة للهدف" value={formatNumber(data.indicators_met, 0)} />
            <Stat label="مؤشرات دون الهدف" value={formatNumber(data.indicators_at_risk, 0)} />
          </div>

          <Card
            title="أداء المحافظات"
            actions={
              <Link to="/comparisons" className="badge">
                المقارنات التفصيلية ←
              </Link>
            }
          >
            {data.governorates.length === 0 ? (
              <div className="empty">لا توجد محافظات في نطاقك.</div>
            ) : (
              <div className="scroll-y">
                <table>
                  <thead>
                    <tr>
                      <th>المحافظة</th>
                      <th>المستشفيات</th>
                      <th>المبلِّغة</th>
                      <th>مؤشرات محققة</th>
                      <th style={{ minWidth: 180 }}>نسبة تحقيق الأهداف</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.governorates.map((g) => (
                      <tr key={g.governorate_name_ar}>
                        <td>{g.governorate_name_ar}</td>
                        <td>{g.hospitals}</td>
                        <td>{g.reported}</td>
                        <td>{g.met}</td>
                        <td>
                          <ComplianceBar percent={g.compliance_percent} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <TopBottom hospitals={data.hospitals} />
        </>
      ) : null}
    </div>
  );
}

function TopBottom({ hospitals }: { hospitals: NationalOverview["hospitals"] }) {
  const ranked = hospitals
    .filter((h) => h.compliance_percent !== null)
    .sort((a, b) => (b.compliance_percent ?? 0) - (a.compliance_percent ?? 0));
  const top = ranked.slice(0, 5);
  const bottom = ranked.slice(-5).reverse();

  return (
    <div className="grid-2">
      <Card title="أعلى المستشفيات أداءً">
        {top.length === 0 ? (
          <div className="empty">لا توجد بيانات كافية للترتيب.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>المستشفى</th>
                <th>المحافظة</th>
                <th>التحقيق</th>
              </tr>
            </thead>
            <tbody>
              {top.map((h) => (
                <tr key={h.hospital_id}>
                  <td>{h.hospital_name_ar}</td>
                  <td>{h.governorate_name_ar ?? "—"}</td>
                  <td>{formatPercent(h.compliance_percent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="أدنى المستشفيات أداءً (تحتاج متابعة)">
        {bottom.length === 0 ? (
          <div className="empty">لا توجد بيانات كافية للترتيب.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>المستشفى</th>
                <th>المحافظة</th>
                <th>التحقيق</th>
              </tr>
            </thead>
            <tbody>
              {bottom.map((h) => (
                <tr key={h.hospital_id}>
                  <td>{h.hospital_name_ar}</td>
                  <td>{h.governorate_name_ar ?? "—"}</td>
                  <td>{formatPercent(h.compliance_percent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
