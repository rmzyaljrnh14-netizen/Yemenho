// Alert centre for the desktop app (v0.9).
//
// The list is computed on the central server from the rows the signed-in user
// may see (late submission, low compliance, quality pressure, indicator trends),
// and every alert carries the numbers it came from. Acknowledging records that
// someone dealt with it. Reading the list needs the network; the rest of the app
// keeps working offline.

import { useCallback, useState } from "react";
import { api } from "../api";
import { useAuth, hasPermission } from "../auth";
import { useAsync } from "../useAsync";
import AlertRulesPanel from "../components/AlertRulesPanel";
import type { Alert, AlertList } from "../types";

const SEVERITY_AR: Record<string, string> = { high: "عالية", medium: "متوسطة", info: "معلومة" };
const SEVERITY_CLASS: Record<string, string> = { high: "badge bad", medium: "badge warn", info: "badge" };
const KIND_AR: Record<string, string> = {
  trend: "اتجاه غير مواتٍ",
  anomaly: "قيمة غير معتادة",
  late_submission: "تأخر إرسال",
  low_compliance: "تدنّي تحقيق الأهداف",
  overdue_capa: "إجراءات تصحيحية متأخرة",
  high_risk: "مخاطر عالية",
  open_incidents: "حوادث مفتوحة",
  open_rca: "تحليل أسباب جذري",
  stale_device: "جهاز مزامنة متأخر",
  open_conflict: "تعارضات مزامنة",
};

const MONTHS_AR = [
  "", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
  "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
];

export default function Alerts() {
  const { me } = useAuth();
  const canManage = hasPermission(me, "alert.manage");
  const canConfigure = hasPermission(me, "alert.configure");
  const hospitalId = me?.scope_org.hospital_id ?? null;

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState<number | null>(now.getMonth() + 1);
  const [showAcked, setShowAcked] = useState(true);
  const [showRules, setShowRules] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(
    () => api.alerts(year, month, hospitalId, true),
    [year, month, hospitalId, refreshKey],
  );
  const list = useAsync<AlertList>(load, [year, month, hospitalId, refreshKey]);

  const alerts = (list.data?.alerts ?? []).filter((a) => showAcked || !a.acked);
  const summary = list.data?.summary;
  const refresh = () => setRefreshKey((k) => k + 1);

  const years: number[] = [];
  for (let y = now.getFullYear() - 4; y <= now.getFullYear() + 1; y += 1) years.push(y);

  return (
    <div>
      <div className="notice-box">
        التنبيهات مشتقّة من بيانات فعلية على الخادم المركزي (تأخر الإرسال، تدنّي تحقيق الأهداف، ضغط الجودة وسلامة
        المرضى، واتجاهات المؤشرات). لا يُولّد النظام أي تنبيه دون أساس في البيانات. يمكن لمن يملك صلاحية إدارة
        التنبيهات الإقرار بمعالجته أو إعادة فتحه.
      </div>

      <div className="card">
        <div className="row">
          <div className="field">
            <label>السنة</label>
            <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>الشهر</label>
            <select
              value={month ?? ""}
              onChange={(e) => setMonth(e.target.value === "" ? null : Number(e.target.value))}
            >
              <option value="">كل السنة</option>
              {MONTHS_AR.slice(1).map((name, i) => (
                <option key={name} value={i + 1}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>العرض</label>
            <select value={showAcked ? "all" : "open"} onChange={(e) => setShowAcked(e.target.value === "all")}>
              <option value="all">الكل</option>
              <option value="open">غير المُقَرّ بها فقط</option>
            </select>
          </div>
          <button onClick={refresh}>تحديث</button>
        </div>
      </div>

      {canConfigure && hospitalId ? (
        <div className="card">
          <div className="row">
            <button onClick={() => setShowRules((v) => !v)}>
              {showRules ? "إخفاء عتبات التنبيه" : "تهيئة عتبات التنبيه"}
            </button>
          </div>
        </div>
      ) : null}
      {canConfigure && showRules && hospitalId ? <AlertRulesPanel hospitalId={hospitalId} /> : null}

      {!hospitalId ? (
        <div className="card">
          <div className="empty">لا يرتبط حسابك بمستشفى، فلا تتوفر تنبيهات.</div>
        </div>
      ) : null}

      {list.loading && !list.data ? (
        <div className="card"><div className="empty">جارٍ جلب التنبيهات...</div></div>
      ) : null}
      {list.error ? (
        <div className="card">
          <div className="error-box">
            تعذّر جلب التنبيهات من الخادم المركزي. يحتاج مركز التنبيهات إلى اتصال بالشبكة، ويمكنك
            متابعة الإدخال والعمل محلياً ثم إعادة المحاولة عند عودة الاتصال.
          </div>
        </div>
      ) : null}

      {summary ? (
        <div className="stat-grid">
          <div className="stat">
            <div className="stat-label">إجمالي التنبيهات</div>
            <div className="stat-value">{summary.total}</div>
          </div>
          <div className="stat">
            <div className="stat-label">عالية الأهمية</div>
            <div className="stat-value">{summary.high}</div>
          </div>
          <div className="stat">
            <div className="stat-label">متوسطة</div>
            <div className="stat-value">{summary.medium}</div>
          </div>
          <div className="stat">
            <div className="stat-label">غير مُقَرّ بها</div>
            <div className="stat-value">{summary.unacknowledged}</div>
          </div>
        </div>
      ) : null}

      {list.data ? (
        <div className="card">
          <h3>قائمة التنبيهات</h3>
          {alerts.length === 0 ? (
            <div className="empty">لا توجد تنبيهات مطابقة لهذه الفترة. 👌</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>الأهمية</th>
                  <th>المصدر</th>
                  <th>النوع</th>
                  <th>التنبيه</th>
                  <th>التفصيل</th>
                  <th>الحالة</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <AlertRow
                    key={a.key}
                    alert={a}
                    year={year}
                    month={month}
                    hospitalId={hospitalId}
                    canManage={canManage}
                    onChanged={refresh}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : null}
    </div>
  );
}

function AlertRow({
  alert,
  year,
  month,
  hospitalId,
  canManage,
  onChanged,
}: {
  alert: Alert;
  year: number;
  month: number | null;
  hospitalId: string | null;
  canManage: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const acknowledge = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.acknowledgeAlert(alert.key, year, month, hospitalId, alert.note_ar ?? undefined);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر الإقرار.");
    } finally {
      setBusy(false);
    }
  };

  const reopen = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.reopenAlert(alert.key, year, month, hospitalId);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر إعادة الفتح.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <tr>
      <td>
        <span className={SEVERITY_CLASS[alert.severity] ?? "badge"}>
          {SEVERITY_AR[alert.severity] ?? alert.severity}
        </span>
      </td>
      <td>{alert.source_label_ar}</td>
      <td>{KIND_AR[alert.kind] ?? alert.kind}</td>
      <td>{alert.title_ar}</td>
      <td className="hint">
        {alert.detail_ar}
        {error ? <div style={{ color: "#b91c1c", marginTop: 4 }}>{error}</div> : null}
      </td>
      <td>
        {alert.acked ? (
          <span className="badge" title={`${alert.acked_by_name ?? ""} — ${alert.acked_at ?? ""}`}>
            مُقَرّ به
          </span>
        ) : (
          <span className="badge warn">مفتوح</span>
        )}
      </td>
      <td>
        {canManage ? (
          alert.acked ? (
            <button onClick={reopen} disabled={busy}>
              إعادة فتح
            </button>
          ) : (
            <button onClick={acknowledge} disabled={busy}>
              إقرار
            </button>
          )
        ) : null}
      </td>
    </tr>
  );
}
