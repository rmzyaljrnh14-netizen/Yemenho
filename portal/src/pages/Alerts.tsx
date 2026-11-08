import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";
import { useAuth, hasPermission } from "../auth";
import PeriodFilter, { currentPeriod } from "../components/PeriodFilter";
import AlertRulesPanel from "../components/AlertRulesPanel";
import { Card, Empty, ErrorBox, Loading, Stat } from "../components/ui";
import type { Alert, AlertList, Hospital } from "../types";

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

export default function Alerts() {
  const { me } = useAuth();
  const canManage = hasPermission(me, "alert.manage");
  const canConfigure = hasPermission(me, "alert.configure");
  const scopedHospital = me?.scope_org.hospital_id ?? null;
  const isCentral = scopedHospital === null;

  const [period, setPeriod] = useState(currentPeriod());
  const [pickedHospital, setPickedHospital] = useState<string>("");
  const [showAcked, setShowAcked] = useState(true);
  const [showRules, setShowRules] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // A hospital user is always locked to their own hospital; a central user may
  // narrow to one hospital or watch the national list.
  const hospitalId = scopedHospital ?? (pickedHospital || null);

  const loadHospitals = useCallback(() => api.hospitals(), []);
  const hospitals = useAsync<Hospital[]>(loadHospitals, []);

  const load = useCallback(
    () => api.alerts(period.year, period.month, hospitalId, true),
    [period.year, period.month, hospitalId, refreshKey],
  );
  const list = useAsync<AlertList>(load, [period.year, period.month, hospitalId, refreshKey]);

  const alerts = (list.data?.alerts ?? []).filter((a) => showAcked || !a.acked);
  const summary = list.data?.summary;

  const refresh = () => setRefreshKey((k) => k + 1);

  return (
    <div>
      <div className="notice-box">
        التنبيهات مشتقّة من بيانات فعلية على الخادم (تأخر الإرسال، تدنّي نسبة تحقيق الأهداف، ضغط الجودة وسلامة
        المرضى، واتجاهات المؤشرات). لا يُولّد النظام أي تنبيه دون أساس في البيانات. يمكن لمن يملك صلاحية إدارة
        التنبيهات الإقرار بمعالجته أو إعادة فتحه.
      </div>

      <div className="toolbar">
        {isCentral ? (
          <div className="field">
            <label>النطاق</label>
            <select value={pickedHospital} onChange={(e) => setPickedHospital(e.target.value)}>
              <option value="">وطني (كل المستشفيات المتاحة)</option>
              {(hospitals.data ?? []).map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name_ar}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div className="field">
          <label>العرض</label>
          <select value={showAcked ? "all" : "open"} onChange={(e) => setShowAcked(e.target.value === "all")}>
            <option value="all">الكل</option>
            <option value="open">غير المُقَرّ بها فقط</option>
          </select>
        </div>
      </div>

      <PeriodFilter value={period} onChange={setPeriod} allowAll />

      {canConfigure ? (
        <div className="toolbar">
          <button onClick={() => setShowRules((v) => !v)}>
            {showRules ? "إخفاء عتبات التنبيه" : "تهيئة عتبات التنبيه"}
          </button>
        </div>
      ) : null}
      {canConfigure && showRules ? <AlertRulesPanel hospitalId={hospitalId} /> : null}

      {list.error ? <ErrorBox message={list.error} /> : null}
      {list.loading && !list.data ? <Loading what="التنبيهات" /> : null}

      {summary ? (
        <div className="stat-grid">
          <Stat label="إجمالي التنبيهات" value={summary.total} />
          <Stat label="عالية الأهمية" value={summary.high} />
          <Stat label="متوسطة" value={summary.medium} />
          <Stat label="غير مُقَرّ بها" value={summary.unacknowledged} />
        </div>
      ) : null}

      <Card
        title={list.data?.scope === "national" ? "التنبيهات الوطنية" : "تنبيهات المستشفى"}
        actions={<button onClick={refresh}>تحديث</button>}
      >
        {alerts.length === 0 ? (
          <Empty message="لا توجد تنبيهات مطابقة لهذه الفترة. 👌" />
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الأهمية</th>
                  <th>المصدر</th>
                  <th>النوع</th>
                  <th>المستشفى</th>
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
                    year={period.year}
                    month={period.month}
                    hospitalId={hospitalId}
                    canManage={canManage}
                    onChanged={refresh}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
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
      <td>{alert.hospital_name_ar ?? "وطني"}</td>
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
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {alert.hospital_id ? (
            <Link
              to={`/hospital/${alert.hospital_id}?year=${year}&month=${month ?? ""}`}
              className="badge"
            >
              تفاصيل
            </Link>
          ) : null}
          {canManage && alert.hospital_id ? (
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
        </div>
      </td>
    </tr>
  );
}
