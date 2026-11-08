import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";
import PeriodFilter, { currentPeriod } from "../components/PeriodFilter";
import { Card, ComplianceBar, ErrorBox, Loading } from "../components/ui";
import { formatPercent, statusLabel } from "../reports";
import type { CompareResponse } from "../types";

type SortKey = "compliance" | "name" | "governorate";

export default function Comparisons() {
  const [period, setPeriod] = useState(currentPeriod());
  const [gov, setGov] = useState<string>("");
  const [sort, setSort] = useState<SortKey>("compliance");

  const load = useCallback(() => api.reportCompare(period.year, period.month), [period.year, period.month]);
  const { data, loading, error } = useAsync<CompareResponse>(load, [period.year, period.month]);

  const governorates = useMemo(() => {
    const set = new Set<string>();
    (data?.hospitals ?? []).forEach((h) => {
      if (h.governorate_name_ar) set.add(h.governorate_name_ar);
    });
    return [...set].sort((a, b) => a.localeCompare(b, "ar"));
  }, [data]);

  const rows = useMemo(() => {
    let list = [...(data?.hospitals ?? [])];
    if (gov) list = list.filter((h) => h.governorate_name_ar === gov);
    list.sort((a, b) => {
      if (sort === "name") return a.hospital_name_ar.localeCompare(b.hospital_name_ar, "ar");
      if (sort === "governorate")
        return (a.governorate_name_ar ?? "").localeCompare(b.governorate_name_ar ?? "", "ar");
      return (b.compliance_percent ?? -1) - (a.compliance_percent ?? -1);
    });
    return list;
  }, [data, gov, sort]);

  const best = rows.find((r) => r.compliance_percent !== null);
  const worst = [...rows].reverse().find((r) => r.compliance_percent !== null);

  return (
    <div>
      <PeriodFilter value={period} onChange={setPeriod} />

      <div className="toolbar">
        <div className="field">
          <label>المحافظة</label>
          <select value={gov} onChange={(e) => setGov(e.target.value)}>
            <option value="">كل المحافظات</option>
            {governorates.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>الترتيب حسب</label>
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            <option value="compliance">نسبة تحقيق الأهداف</option>
            <option value="name">اسم المستشفى</option>
            <option value="governorate">المحافظة</option>
          </select>
        </div>
      </div>

      {error ? <ErrorBox message={error} /> : null}
      {loading && !data ? <Loading what="المقارنات" /> : null}

      {data ? (
        <>
          <div className="grid-2" style={{ marginBottom: 18 }}>
            <div className="stat">
              <div className="stat-label">أعلى مستشفى تحقيقاً للأهداف</div>
              <div className="stat-value" style={{ fontSize: 18 }}>
                {best?.hospital_name_ar ?? "—"}
              </div>
              <div className="stat-sub">
                {best ? `${formatPercent(best.compliance_percent)} — ${best.governorate_name_ar ?? ""}` : "لا بيانات"}
              </div>
            </div>
            <div className="stat">
              <div className="stat-label">أدنى مستشفى تحقيقاً للأهداف</div>
              <div className="stat-value" style={{ fontSize: 18 }}>
                {worst?.hospital_name_ar ?? "—"}
              </div>
              <div className="stat-sub">
                {worst ? `${formatPercent(worst.compliance_percent)} — ${worst.governorate_name_ar ?? ""}` : "لا بيانات"}
              </div>
            </div>
          </div>

          <Card title={`مقارنة المستشفيات (${rows.length})`}>
            {rows.length === 0 ? (
              <div className="empty">لا توجد مستشفيات مطابقة.</div>
            ) : (
              <div className="scroll-y">
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>المستشفى</th>
                      <th>المحافظة</th>
                      <th>حالة الفترة</th>
                      <th>مؤشرات محققة</th>
                      <th style={{ minWidth: 190 }}>نسبة تحقيق الأهداف</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={r.hospital_id}>
                        <td>{i + 1}</td>
                        <td>{r.hospital_name_ar}</td>
                        <td>{r.governorate_name_ar ?? "—"}</td>
                        <td>
                          {r.reported ? (
                            <span className="badge on">{statusLabel(r.period_status)}</span>
                          ) : (
                            <span className="badge off">لم تُرسل</span>
                          )}
                        </td>
                        <td>
                          {r.indicators_met} / {r.indicators_with_value}
                        </td>
                        <td>
                          <ComplianceBar percent={r.compliance_percent} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}
