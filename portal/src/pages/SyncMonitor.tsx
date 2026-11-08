import { useCallback, useState } from "react";
import { api } from "../api";
import { useAuth, hasPermission } from "../auth";
import { useAsync } from "../lib/useAsync";
import { Card, Empty, ErrorBox, Loading, Stat } from "../components/ui";
import type { SyncConflict, SyncConflictPage, SyncDevice, SyncMonitorOverview } from "../types";

const PAGE_SIZE = 50;

function fmtDate(value: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("ar");
  } catch {
    return value;
  }
}

function agoAr(days: number | null): string {
  if (days === null) return "لم يُرَ بعد";
  if (days === 0) return "اليوم";
  if (days === 1) return "قبل يوم";
  if (days === 2) return "قبل يومين";
  return `قبل ${days} يوماً`;
}

// National sync monitor (v0.12): device health and conflict review.
export default function SyncMonitor() {
  const { me } = useAuth();
  const canManage = hasPermission(me, "sync.manage");

  const [onlyStale, setOnlyStale] = useState(false);
  const [includeResolved, setIncludeResolved] = useState(false);
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadOverview = useCallback(() => api.syncOverview(), []);
  const loadDevices = useCallback(() => api.syncDevices(onlyStale), [onlyStale]);
  const loadConflicts = useCallback(
    () => api.syncConflicts({ includeResolved, limit: PAGE_SIZE, offset }),
    [includeResolved, offset],
  );

  const overview = useAsync<SyncMonitorOverview>(loadOverview, []);
  const devices = useAsync<SyncDevice[]>(loadDevices, [onlyStale]);
  const conflicts = useAsync<SyncConflictPage>(loadConflicts, [includeResolved, offset]);

  const entries = conflicts.data?.entries ?? [];
  const total = conflicts.data?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = offset + entries.length;

  const resolve = async (id: string, resolution: "reviewed" | "dismissed") => {
    setActionError(null);
    setNotice(null);
    setBusyId(id);
    try {
      await api.resolveSyncConflict(id, { resolution });
      setNotice(resolution === "reviewed" ? "تم تسجيل مراجعة التعارض." : "تم استبعاد التعارض بلا إجراء.");
      conflicts.reload();
      overview.reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "تعذّر تنفيذ الإجراء.");
    } finally {
      setBusyId(null);
    }
  };

  const ov = overview.data;

  return (
    <div>
      <div className="stat-grid">
        <Stat label="إجمالي الأجهزة" value={ov?.devices_total ?? "—"} />
        <Stat label="أجهزة منتظمة" value={ov?.devices_ok ?? "—"} />
        <Stat
          label={`أجهزة متأخرة (≥ ${ov?.stale_days ?? 7} أيام)`}
          value={ov?.devices_stale ?? "—"}
        />
        <Stat label="تعارضات مفتوحة" value={ov?.open_conflicts ?? "—"} />
        <Stat label="تعارضات مُعالَجة" value={ov?.resolved_conflicts ?? "—"} />
      </div>

      <Card
        title="حالة أجهزة المزامنة"
        actions={
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={onlyStale}
              onChange={(e) => setOnlyStale(e.target.checked)}
            />
            عرض المتأخرة فقط
          </label>
        }
      >
        {devices.error ? <ErrorBox message={devices.error} /> : null}
        {devices.loading && !devices.data ? <Loading what="الأجهزة" /> : null}
        {devices.data && devices.data.length === 0 ? (
          <Empty message="لا توجد أجهزة مسجّلة في نطاقك بعد." />
        ) : null}
        {devices.data && devices.data.length > 0 ? (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الجهاز</th>
                  <th>المستشفى</th>
                  <th>آخر مزامنة</th>
                  <th>منذ</th>
                  <th>آخر رقم تغيير</th>
                  <th>الحالة</th>
                </tr>
              </thead>
              <tbody>
                {devices.data.map((d) => (
                  <tr key={d.node_id}>
                    <td>{d.name ?? d.node_id}</td>
                    <td>{d.hospital_name_ar ?? "—"}</td>
                    <td>{fmtDate(d.last_seen_at)}</td>
                    <td>{agoAr(d.days_since_seen)}</td>
                    <td>{d.last_seq}</td>
                    <td>
                      <span className={`badge ${d.status === "stale" ? "bad" : "ok"}`}>
                        {d.status_label_ar}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      <Card
        title={`تعارضات المزامنة (${shownFrom}–${shownTo} من ${total})`}
        actions={
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={includeResolved}
                onChange={(e) => {
                  setIncludeResolved(e.target.checked);
                  setOffset(0);
                }}
              />
              إظهار المُعالَجة
            </label>
            <button className="btn ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              السابق
            </button>
            <button className="btn ghost" disabled={shownTo >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
              التالي
            </button>
          </div>
        }
      >
        {notice ? <div className="notice-box">{notice}</div> : null}
        {actionError ? <ErrorBox message={actionError} /> : null}
        {conflicts.error ? <ErrorBox message={conflicts.error} /> : null}
        {conflicts.loading && !conflicts.data ? <Loading what="التعارضات" /> : null}
        {conflicts.data && entries.length === 0 ? (
          <Empty message="لا توجد تعارضات مطابقة. المزامنة سليمة." />
        ) : null}
        {entries.length > 0 ? (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الوقت</th>
                  <th>الكيان</th>
                  <th>المستشفى</th>
                  <th>الجهاز</th>
                  <th>الحالة</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {entries.map((c) => (
                  <ConflictRow
                    key={c.id}
                    conflict={c}
                    isOpen={openId === c.id}
                    onToggle={() => setOpenId(openId === c.id ? null : c.id)}
                    canManage={canManage}
                    busy={busyId === c.id}
                    onResolve={resolve}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      <p className="hint">
        يعرض هذا المركز حالة مزامنة الأجهزة والتعارضات المسجّلة عند إرسال تعديلات متعارضة. حلّ التعارض
        يسجّل أنّ مسؤولاً راجعه ولا يغيّر البيانات المعتمدة. ترى بيانات نطاقك فقط وفق عزل البيانات (RLS).
      </p>
    </div>
  );
}

function ConflictRow({
  conflict,
  isOpen,
  onToggle,
  canManage,
  busy,
  onResolve,
}: {
  conflict: SyncConflict;
  isOpen: boolean;
  onToggle: () => void;
  canManage: boolean;
  busy: boolean;
  onResolve: (id: string, resolution: "reviewed" | "dismissed") => void;
}) {
  const open = conflict.resolution === "auto_server";
  return (
    <>
      <tr>
        <td>{fmtDate(conflict.created_at)}</td>
        <td>{conflict.entity_label_ar}</td>
        <td>{conflict.hospital_name_ar ?? "—"}</td>
        <td>{conflict.node_id ?? "—"}</td>
        <td>
          <span className={`badge ${open ? "warn" : "ok"}`}>{conflict.resolution_label_ar}</span>
        </td>
        <td>
          <button className="btn ghost" onClick={onToggle}>
            {isOpen ? "إخفاء" : "التفاصيل"}
          </button>
        </td>
      </tr>
      {isOpen ? (
        <tr>
          <td colSpan={6}>
            <div>
              <div>
                <strong>القيمة على الجهاز (المرفوضة):</strong>
                <pre
                  style={{
                    direction: "ltr",
                    textAlign: "left",
                    fontFamily: "monospace",
                    fontSize: 12,
                    background: "var(--surface-2, #f6f8f7)",
                    padding: 8,
                    borderRadius: 6,
                    overflowX: "auto",
                  }}
                >
                  {JSON.stringify(conflict.local_payload, null, 2)}
                </pre>
              </div>
              <div>
                <strong>القيمة على الخادم (المعتمدة):</strong>
                <pre
                  style={{
                    direction: "ltr",
                    textAlign: "left",
                    fontFamily: "monospace",
                    fontSize: 12,
                    background: "var(--surface-2, #f6f8f7)",
                    padding: 8,
                    borderRadius: 6,
                    overflowX: "auto",
                  }}
                >
                  {JSON.stringify(conflict.server_payload, null, 2)}
                </pre>
              </div>
              {conflict.resolved_by_name ? (
                <p className="hint">
                  راجعه: {conflict.resolved_by_name} — {fmtDate(conflict.resolved_at)}
                </p>
              ) : null}
              {open && canManage ? (
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn" disabled={busy} onClick={() => onResolve(conflict.id, "reviewed")}>
                    تسجيل المراجعة
                  </button>
                  <button className="btn ghost" disabled={busy} onClick={() => onResolve(conflict.id, "dismissed")}>
                    استبعاد بلا إجراء
                  </button>
                </div>
              ) : null}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
