import type { ReactNode } from "react";

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="card">
      {(title || actions) && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
          {title ? <h3 style={{ margin: 0 }}>{title}</h3> : <span />}
          {actions}
        </div>
      )}
      <div style={{ marginTop: title ? 12 : 0 }}>{children}</div>
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub ? <div className="stat-sub">{sub}</div> : null}
    </div>
  );
}

export function Loading({ what = "البيانات" }: { what?: string }) {
  return <div className="empty">جارٍ تحميل {what}...</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="error-box">{message}</div>;
}

export function Empty({ message }: { message: string }) {
  return <div className="empty">{message}</div>;
}

export function ComplianceBar({ percent }: { percent: number | null }) {
  const pct = percent === null ? 0 : Math.max(0, Math.min(100, percent));
  const color = percent === null ? "#94a3b8" : pct >= 85 ? "#15803d" : pct >= 70 ? "#b45309" : "#b91c1c";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div className="progress" style={{ flex: 1 }}>
        <span style={{ width: `${pct}%`, background: color }} />
      </div>
      <span style={{ minWidth: 52, textAlign: "left", color }}>
        {percent === null ? "—" : `${percent.toFixed(1)}%`}
      </span>
    </div>
  );
}
