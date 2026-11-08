import { MONTHS_AR } from "../reports";

export interface PeriodSelection {
  year: number;
  month: number | null;
}

export function currentPeriod(): PeriodSelection {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

export default function PeriodFilter({
  value,
  onChange,
  allowAll = false,
}: {
  value: PeriodSelection;
  onChange: (next: PeriodSelection) => void;
  allowAll?: boolean;
}) {
  const years = [];
  const y = new Date().getFullYear();
  for (let i = y - 4; i <= y + 1; i += 1) years.push(i);

  return (
    <div className="toolbar">
      <div className="field">
        <label>السنة</label>
        <select value={value.year} onChange={(e) => onChange({ ...value, year: Number(e.target.value) })}>
          {years.map((yy) => (
            <option key={yy} value={yy}>
              {yy}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>الشهر</label>
        <select
          value={value.month ?? ""}
          onChange={(e) => onChange({ ...value, month: e.target.value === "" ? null : Number(e.target.value) })}
        >
          {allowAll ? <option value="">كل السنة</option> : null}
          {MONTHS_AR.map((name, i) => (
            <option key={name} value={i + 1}>
              {name}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
