// Sync status page (v0.6): shows the local database, what is queued, what failed
// and any conflicts, and lets the person run a sync or export a local backup.

import { useEffect, useState } from "react";
import { desktop, isDesktop, type LocalConflict, type PendingOp } from "../desktop";
import { useSync } from "../useSync";

const OP_LABEL: Record<string, string> = {
  reporting_period: "فترة تقرير",
  indicator_value: "قيمة مؤشر",
};

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ar");
  } catch {
    return iso;
  }
}

export default function SyncSettings() {
  const sync = useSync();
  const [pending, setPending] = useState<PendingOp[]>([]);
  const [conflicts, setConflicts] = useState<LocalConflict[]>([]);

  async function reload() {
    setPending((await desktop.pendingOps(true)) ?? []);
    setConflicts((await desktop.listConflicts()) ?? []);
  }

  useEffect(() => {
    void reload();
  }, [sync.status]);

  async function exportBackup() {
    const backup = await desktop.exportBackup();
    if (!backup) return;
    const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `yhq-local-backup-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  if (!isDesktop()) {
    return (
      <div className="card">
        <h3>المزامنة والعمل دون إنترنت</h3>
        <p className="hint">
          هذه الميزة متاحة داخل تطبيق سطح المكتب المثبّت على Windows. عند تشغيل الواجهة في المتصفح
          تعمل المنصة بالاتصال المباشر بالخادم فقط.
        </p>
      </div>
    );
  }

  const status = sync.status;
  const online = sync.online;

  return (
    <div>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>حالة المزامنة</h3>
          <div className="row" style={{ gap: 8 }}>
            <span className={`badge ${online ? "on" : "off"}`}>
              {online ? "متصل بالإنترنت" : "دون إنترنت"}
            </span>
            <button className="primary" disabled={sync.busy} onClick={() => sync.syncNow()}>
              {sync.busy ? "جارٍ المزامنة..." : "مزامنة الآن"}
            </button>
          </div>
        </div>
        <div className="stat-grid" style={{ marginTop: 12 }}>
          <div className="stat">
            <span className="stat-value">{status?.pending_count ?? 0}</span>
            <span className="hint">عمليات بانتظار الإرسال</span>
          </div>
          <div className="stat">
            <span className="stat-value">{status?.failed_count ?? 0}</span>
            <span className="hint">عمليات متعذّرة</span>
          </div>
          <div className="stat">
            <span className="stat-value">{status?.conflict_count ?? 0}</span>
            <span className="hint">تعارضات مُسجّلة</span>
          </div>
          <div className="stat">
            <span className="stat-value">{status?.cursor ?? 0}</span>
            <span className="hint">مؤشر آخر مزامنة</span>
          </div>
        </div>
        <p className="hint" style={{ marginTop: 10 }}>
          آخر مزامنة ناجحة: {fmt(status?.last_sync_at)} — رقم الجهاز: {status?.node_id ?? "—"}
        </p>
        {sync.lastOutcome?.message && (
          <div className={sync.lastOutcome.ok ? "notice-box" : "error-box"}>
            {sync.lastOutcome.message}
          </div>
        )}
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>العمليات غير المُرسَلة أو المتعذّرة</h3>
          <button onClick={() => void reload()}>تحديث</button>
        </div>
        {pending.length === 0 ? (
          <div className="empty">لا توجد عمليات معلّقة. جميع البيانات مُزامنة.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>النوع</th>
                <th>الحالة</th>
                <th>المحاولات</th>
                <th>ملاحظة</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((op) => (
                <tr key={op.op_id}>
                  <td>{OP_LABEL[op.entity_type] ?? op.entity_type}</td>
                  <td>
                    <span className={`badge ${op.state === "failed" ? "off" : "warn"}`}>
                      {op.state === "failed" ? "متعذّرة" : "بانتظار الإرسال"}
                    </span>
                  </td>
                  <td>{op.attempts}</td>
                  <td className="hint">{op.last_error ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>التعارضات</h3>
        {conflicts.length === 0 ? (
          <div className="empty">لا توجد تعارضات.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>النوع</th>
                <th>المعالجة</th>
                <th>التاريخ</th>
              </tr>
            </thead>
            <tbody>
              {conflicts.map((c) => (
                <tr key={c.id}>
                  <td>{OP_LABEL[c.entity_type] ?? c.entity_type}</td>
                  <td>اعتُمدت نسخة الخادم</td>
                  <td className="hint">{fmt(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>النسخ الاحتياطي المحلي</h3>
        <p className="hint">
          يُنشئ ملفاً يحتوي مكتبة المؤشرات والعمليات المعلّقة. احفظه في مكان آمن قبل إعادة تثبيت
          الجهاز.
        </p>
        <button onClick={() => void exportBackup()}>تنزيل نسخة احتياطية محلية</button>
      </div>
    </div>
  );
}
