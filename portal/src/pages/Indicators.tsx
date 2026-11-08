import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { hasPermission, useAuth } from "../auth";
import { useAsync } from "../lib/useAsync";
import { Card, Empty, ErrorBox, Loading } from "../components/ui";
import { formatNumber } from "../reports";
import type { Computation, Direction, Frequency, Indicator } from "../types";

const COMPUTATION_AR: Record<Computation, string> = {
  ratio: "نسبة (بسط/مقام)",
  rate: "معدل",
  percent: "نسبة مئوية",
  count: "عدد",
  average: "متوسط",
  sum: "مجموع",
  entered: "إدخال مباشر",
};

const DIRECTION_AR: Record<Direction, string> = {
  higher_better: "الارتفاع أفضل",
  lower_better: "الانخفاض أفضل",
  target_range: "نطاق مستهدف",
};

const FREQUENCY_AR: Record<Frequency, string> = {
  monthly: "شهرية",
  quarterly: "ربعية",
  semi_annual: "نصف سنوية",
  annual: "سنوية",
};

export default function Indicators() {
  const { me } = useAuth();
  const canManage = hasPermission(me, "indicator.manage");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Indicator | null>(null);

  const load = useCallback(() => api.indicators(search || undefined), [search]);
  const { data, loading, error, reload } = useAsync<Indicator[]>(load, [search]);

  const grouped = useMemo(() => data ?? [], [data]);

  return (
    <div>
      <div className="notice-box">
        المكتبة الوطنية للمؤشرات: تُنشأ هنا مرة واحدة، ثم تُسند للمستشفيات والأقسام من صفحة «المستشفيات والأقسام».
        دعم أنواع حساب متعددة واتجاه تحسّن مختلف لكل مؤشر.
      </div>

      <Card
        title={`مكتبة المؤشرات الوطنية (${grouped.length})`}
        actions={
          <div className="field" style={{ margin: 0, minWidth: 240 }}>
            <input
              placeholder="بحث بالاسم أو الرمز..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        }
      >
        {canManage ? <NewIndicatorForm onDone={reload} /> : null}
        {error ? <ErrorBox message={error} /> : null}
        {loading && !data ? <Loading what="المكتبة" /> : null}
        {data && data.length === 0 ? <Empty message="لا توجد مؤشرات مطابقة." /> : null}
        {data && data.length > 0 ? (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الرمز</th>
                  <th>المؤشر</th>
                  <th>نوع الحساب</th>
                  <th>الوحدة</th>
                  <th>الدورية</th>
                  <th>الهدف</th>
                  <th>الاتجاه</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((i) => (
                  <tr key={i.id}>
                    <td>{i.code}</td>
                    <td>{i.name_ar}</td>
                    <td className="hint">{COMPUTATION_AR[i.computation]}</td>
                    <td>{i.unit_ar ?? "—"}</td>
                    <td className="hint">{FREQUENCY_AR[i.frequency]}</td>
                    <td>{formatNumber(i.target_value)}</td>
                    <td>
                      <span className="badge">{DIRECTION_AR[i.direction]}</span>
                    </td>
                    <td>
                      <button onClick={() => setSelected(i)}>تفاصيل</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      {selected ? (
        <Card title={`${selected.code} — ${selected.name_ar}`}>
          <dl className="kv">
            <dt>التعريف</dt>
            <dd>{selected.definition_ar ?? "—"}</dd>
            <dt>الهدف من المؤشر</dt>
            <dd>{selected.purpose_ar ?? "—"}</dd>
            <dt>طريقة القياس والحساب</dt>
            <dd>{selected.calculation_ar ?? "—"}</dd>
            <dt>نوع الحساب</dt>
            <dd>{COMPUTATION_AR[selected.computation]}</dd>
            <dt>وحدة القياس</dt>
            <dd>{selected.unit_ar ?? "—"}</dd>
            <dt>مصدر البيانات</dt>
            <dd>{selected.data_source_ar ?? "—"}</dd>
            <dt>دورية القياس</dt>
            <dd>{FREQUENCY_AR[selected.frequency]}</dd>
            <dt>الجهة المسؤولة</dt>
            <dd>{selected.responsible_party_ar ?? "—"}</dd>
            <dt>القيمة المستهدفة</dt>
            <dd>{formatNumber(selected.target_value)}</dd>
            <dt>الحدود المقبولة</dt>
            <dd>
              {selected.acceptable_min ?? "—"} إلى {selected.acceptable_max ?? "—"}
            </dd>
            <dt>اتجاه التحسن</dt>
            <dd>{DIRECTION_AR[selected.direction]}</dd>
            {selected.computation !== "entered" && selected.computation !== "count" ? (
              <>
                <dt>البسط</dt>
                <dd>{selected.numerator_label_ar ?? "—"}</dd>
                <dt>المقام</dt>
                <dd>{selected.denominator_label_ar ?? "—"}</dd>
              </>
            ) : null}
          </dl>
        </Card>
      ) : null}
    </div>
  );
}

function NewIndicatorForm({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    code: "",
    name_ar: "",
    computation: "percent" as Computation,
    direction: "higher_better" as Direction,
    frequency: "monthly" as Frequency,
    unit_ar: "",
    target_value: "",
    acceptable_min: "",
    acceptable_max: "",
    definition_ar: "",
    calculation_ar: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createIndicator({
        code: form.code.trim(),
        name_ar: form.name_ar.trim(),
        computation: form.computation,
        direction: form.direction,
        frequency: form.frequency,
        unit_ar: form.unit_ar.trim() || null,
        definition_ar: form.definition_ar.trim() || null,
        calculation_ar: form.calculation_ar.trim() || null,
        target_value: form.target_value === "" ? null : Number(form.target_value),
        acceptable_min: form.acceptable_min === "" ? null : Number(form.acceptable_min),
        acceptable_max: form.acceptable_max === "" ? null : Number(form.acceptable_max),
      });
      setForm({ ...form, code: "", name_ar: "", unit_ar: "", target_value: "", definition_ar: "", calculation_ar: "" });
      setOpen(false);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذّر إنشاء المؤشر.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="primary" onClick={() => setOpen(true)} style={{ marginBottom: 14 }}>
        + مؤشر وطني جديد
      </button>
    );
  }

  return (
    <form onSubmit={submit} style={{ marginBottom: 16 }}>
      {error ? <ErrorBox message={error} /> : null}
      <div className="row">
        <div className="field">
          <label>الرمز</label>
          <input value={form.code} onChange={(e) => set("code", e.target.value)} required />
        </div>
        <div className="field" style={{ flexBasis: 280 }}>
          <label>اسم المؤشر</label>
          <input value={form.name_ar} onChange={(e) => set("name_ar", e.target.value)} required />
        </div>
        <div className="field">
          <label>نوع الحساب</label>
          <select value={form.computation} onChange={(e) => set("computation", e.target.value as Computation)}>
            {Object.entries(COMPUTATION_AR).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>اتجاه التحسن</label>
          <select value={form.direction} onChange={(e) => set("direction", e.target.value as Direction)}>
            {Object.entries(DIRECTION_AR).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>الدورية</label>
          <select value={form.frequency} onChange={(e) => set("frequency", e.target.value as Frequency)}>
            {Object.entries(FREQUENCY_AR).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>وحدة القياس</label>
          <input value={form.unit_ar} onChange={(e) => set("unit_ar", e.target.value)} />
        </div>
        <div className="field">
          <label>القيمة المستهدفة</label>
          <input
            type="number"
            step="any"
            value={form.target_value}
            onChange={(e) => set("target_value", e.target.value)}
          />
        </div>
        <div className="field">
          <label>الحد الأدنى المقبول</label>
          <input
            type="number"
            step="any"
            value={form.acceptable_min}
            onChange={(e) => set("acceptable_min", e.target.value)}
          />
        </div>
        <div className="field">
          <label>الحد الأعلى المقبول</label>
          <input
            type="number"
            step="any"
            value={form.acceptable_max}
            onChange={(e) => set("acceptable_max", e.target.value)}
          />
        </div>
      </div>
      <div className="field">
        <label>التعريف</label>
        <input value={form.definition_ar} onChange={(e) => set("definition_ar", e.target.value)} />
      </div>
      <div className="field">
        <label>طريقة القياس والحساب</label>
        <input value={form.calculation_ar} onChange={(e) => set("calculation_ar", e.target.value)} />
      </div>
      <div className="row">
        <button className="primary" type="submit" disabled={busy}>
          حفظ المؤشر
        </button>
        <button type="button" onClick={() => setOpen(false)}>
          إلغاء
        </button>
      </div>
    </form>
  );
}
