import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { hasPermission, useAuth } from "../auth";
import type { Direction, Indicator } from "../types";

const DIRECTION_LABEL: Record<Direction, string> = {
  higher_better: "ارتفاعه أفضل",
  lower_better: "انخفاضه أفضل",
  target_range: "نطاق مستهدف",
};

const COMPUTATION_LABEL: Record<string, string> = {
  ratio: "نسبة",
  rate: "معدل",
  percent: "نسبة مئوية",
  count: "عدد",
  average: "متوسط",
  sum: "مجموع",
  entered: "إدخال مباشر",
};

const FREQ_LABEL: Record<string, string> = {
  monthly: "شهري",
  quarterly: "ربعي",
  semi_annual: "نصف سنوي",
  annual: "سنوي",
};

export default function Indicators() {
  const { me } = useAuth();
  const canManage = hasPermission(me, "indicator.manage");
  const [rows, setRows] = useState<Indicator[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Indicator | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const list = await api.indicators();
        setRows(list);
        setSelected((prev) => prev ?? list[0] ?? null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل المؤشرات.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) => r.name_ar.toLowerCase().includes(q) || r.code.toLowerCase().includes(q),
    );
  }, [rows, search]);

  return (
    <div className="grid-2">
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>مكتبة المؤشرات الوطنية</h3>
          <span className="chip">{filtered.length} مؤشر</span>
        </div>
        <div className="field" style={{ marginTop: 12 }}>
          <input
            placeholder="ابحث بالاسم أو الرمز..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {error && <div className="error-box">{error}</div>}
        {loading ? (
          <div className="empty">جارٍ التحميل...</div>
        ) : filtered.length === 0 ? (
          <div className="empty">لا توجد نتائج.</div>
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الرمز</th>
                  <th>المؤشر</th>
                  <th>الاتجاه</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => setSelected(r)}
                    style={{ cursor: "pointer", background: selected?.id === r.id ? "#ecfdf5" : undefined }}
                  >
                    <td className="hint">{r.code}</td>
                    <td>{r.name_ar}</td>
                    <td>
                      <span className={`badge ${r.direction === "lower_better" ? "off" : "on"}`}>
                        {DIRECTION_LABEL[r.direction]}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        {!selected ? (
          <div className="empty">اختر مؤشراً لعرض تفاصيله.</div>
        ) : (
          <>
            <h3 style={{ marginTop: 0 }}>{selected.name_ar}</h3>
            <p className="hint" style={{ marginTop: -6 }}>
              {selected.code}
            </p>
            <dl className="kv">
              <dt>التعريف</dt>
              <dd>{selected.definition_ar ?? "—"}</dd>
              <dt>الهدف من القياس</dt>
              <dd>{selected.purpose_ar ?? "—"}</dd>
              <dt>طريقة القياس</dt>
              <dd>{selected.calculation_ar ?? "—"}</dd>
              <dt>نوع الحساب</dt>
              <dd>{COMPUTATION_LABEL[selected.computation] ?? selected.computation}</dd>
              <dt>وحدة القياس</dt>
              <dd>{selected.unit_ar ?? "—"}</dd>
              <dt>مصدر البيانات</dt>
              <dd>{selected.data_source_ar ?? "—"}</dd>
              <dt>دورية القياس</dt>
              <dd>{FREQ_LABEL[selected.frequency] ?? selected.frequency}</dd>
              <dt>الجهة المسؤولة</dt>
              <dd>{selected.responsible_party_ar ?? "—"}</dd>
              <dt>اتجاه التحسن</dt>
              <dd>{DIRECTION_LABEL[selected.direction]}</dd>
              <dt>القيمة المستهدفة</dt>
              <dd>{selected.target_value ?? "—"}</dd>
              <dt>الحدود المقبولة</dt>
              <dd>
                {selected.acceptable_min ?? "—"} إلى {selected.acceptable_max ?? "—"}
              </dd>
            </dl>
            {!canManage && (
              <p className="hint">تعديل المكتبة متاح لمدير النظام المركزي أو من يملك صلاحية إدارة المؤشرات.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
