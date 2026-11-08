import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth, hasPermission } from "../auth";
import { useAsync } from "../lib/useAsync";
import { Card, Empty, ErrorBox, Loading, Stat } from "../components/ui";
import type { AuditEntry, AuditFacets, AuditLogPage } from "../types";

const PAGE_SIZE = 50;

interface Filters {
  entityType: string;
  action: string;
  actorUserId: string;
  hospitalId: string;
  since: string;
  until: string;
  q: string;
}

const EMPTY: Filters = {
  entityType: "",
  action: "",
  actorUserId: "",
  hospitalId: "",
  since: "",
  until: "",
  q: "",
};

function toParams(f: Filters, offset: number) {
  return {
    entityType: f.entityType || undefined,
    action: f.action || undefined,
    actorUserId: f.actorUserId || undefined,
    hospitalId: f.hospitalId || undefined,
    since: f.since ? new Date(f.since).toISOString() : undefined,
    until: f.until ? new Date(f.until).toISOString() : undefined,
    q: f.q || undefined,
    limit: PAGE_SIZE,
    offset,
  };
}

export default function Audit() {
  const { me } = useAuth();
  const isCentral = me?.scope_org.level === "central";
  const canExport = hasPermission(me, "audit.view");

  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const loadPage = useCallback(() => api.auditLog(toParams(filters, offset)), [filters, offset]);
  const loadFacets = useCallback(() => api.auditFacets(), []);

  const page = useAsync<AuditLogPage>(loadPage, [filters, offset]);
  const facets = useAsync<AuditFacets>(loadFacets, []);

  const entries = page.data?.entries ?? [];
  const total = page.data?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = offset + entries.length;

  const entityLabel = useMemo(() => {
    const map = new Map<string, string>();
    (facets.data?.entity_types ?? []).forEach((f) => map.set(f.code, f.label_ar));
    return map;
  }, [facets.data]);

  const apply = () => {
    setFilters(draft);
    setOffset(0);
    setOpenId(null);
  };

  const reset = () => {
    setDraft(EMPTY);
    setFilters(EMPTY);
    setOffset(0);
    setOpenId(null);
  };

  const doExport = async (format: "csv" | "xlsx") => {
    setExportError(null);
    try {
      await api.exportAuditLog(format, toParams(filters, 0));
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "تعذّر إنشاء الملف.");
    }
  };

  return (
    <div>
      <div className="stat-grid">
        <Stat label="عدد المدخلات في نطاقك" value={total} />
        <Stat label="معروض الآن" value={entries.length} />
        <Stat label="أنواع الكيانات" value={facets.data?.entity_types.length ?? 0} />
        <Stat label="الإجراءات" value={facets.data?.actions.length ?? 0} />
      </div>

      <Card title="عوامل التصفية">
        <div className="toolbar" style={{ flexWrap: "wrap", gap: 12 }}>
          <div className="field">
            <label>نوع الكيان</label>
            <select
              value={draft.entityType}
              onChange={(e) => setDraft({ ...draft, entityType: e.target.value })}
            >
              <option value="">كل الأنواع</option>
              {(facets.data?.entity_types ?? []).map((f) => (
                <option key={f.code} value={f.code}>
                  {f.label_ar} ({f.count})
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>الإجراء</label>
            <select value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })}>
              <option value="">كل الإجراءات</option>
              {(facets.data?.actions ?? []).map((f) => (
                <option key={f.code} value={f.code}>
                  {f.label_ar} ({f.count})
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>المستخدم</label>
            <select
              value={draft.actorUserId}
              onChange={(e) => setDraft({ ...draft, actorUserId: e.target.value })}
            >
              <option value="">كل المستخدمين</option>
              {(facets.data?.actors ?? []).map((a) => (
                <option key={a.user_id} value={a.user_id}>
                  {a.name} ({a.count})
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>من تاريخ</label>
            <input
              type="datetime-local"
              value={draft.since}
              onChange={(e) => setDraft({ ...draft, since: e.target.value })}
            />
          </div>

          <div className="field">
            <label>إلى تاريخ</label>
            <input
              type="datetime-local"
              value={draft.until}
              onChange={(e) => setDraft({ ...draft, until: e.target.value })}
            />
          </div>

          <div className="field">
            <label>بحث</label>
            <input
              type="text"
              placeholder="معرّف السجل أو كلمة"
              value={draft.q}
              onChange={(e) => setDraft({ ...draft, q: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Enter") apply();
              }}
            />
          </div>

          <div className="field" style={{ alignSelf: "flex-end" }}>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn" onClick={apply}>
                تطبيق
              </button>
              <button className="btn ghost" onClick={reset}>
                إعادة تعيين
              </button>
              {canExport ? (
                <>
                  <button className="btn ghost" onClick={() => doExport("xlsx")}>
                    تصدير Excel
                  </button>
                  <button className="btn ghost" onClick={() => doExport("csv")}>
                    تصدير CSV
                  </button>
                </>
              ) : null}
            </div>
          </div>
        </div>
        {exportError ? <ErrorBox message={exportError} /> : null}
      </Card>

      <Card
        title={`سجل التدقيق (${shownFrom}–${shownTo} من ${total})`}
        actions={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn ghost"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              السابق
            </button>
            <button
              className="btn ghost"
              disabled={shownTo >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              التالي
            </button>
          </div>
        }
      >
        {page.error ? <ErrorBox message={page.error} /> : null}
        {page.loading && !page.data ? <Loading what="السجل" /> : null}
        {page.data && entries.length === 0 ? <Empty message="لا توجد مدخلات مطابقة." /> : null}
        {entries.length > 0 ? (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>الوقت</th>
                  <th>المستخدم</th>
                  <th>الملخّص</th>
                  <th>الإجراء</th>
                  <th>المستشفى</th>
                  <th>المصدر</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <EntryRow
                    key={e.id}
                    entry={e}
                    entityLabel={entityLabel.get(e.entity_type) ?? e.entity_label_ar}
                    isOpen={openId === e.id}
                    onToggle={() => setOpenId(openId === e.id ? null : e.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      <p className="hint">
        السجل للقراءة فقط ولا يمكن تعديله أو حذفه، ويقتصر على نطاقك وفق الصلاحيات وعزل البيانات (RLS):{" "}
        {isCentral ? "أنت في الإدارة المركزية وترى كل المستشفيات." : "ترى بيانات نطاقك فقط."}
      </p>
    </div>
  );
}

function EntryRow({
  entry,
  entityLabel,
  isOpen,
  onToggle,
}: {
  entry: AuditEntry;
  entityLabel: string;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const detail = entry.after ?? entry.before;
  return (
    <>
      <tr>
        <td className="hint">{new Date(entry.at).toLocaleString("ar")}</td>
        <td>{entry.actor_name ?? "—"}</td>
        <td>
          {entry.summary_ar}
          <span className="hint" style={{ marginInlineStart: 6 }}>
            ({entityLabel})
          </span>
        </td>
        <td>
          <span className="badge">{entry.action_label_ar}</span>
        </td>
        <td className="hint">{entry.hospital_name_ar ?? "—"}</td>
        <td className="hint">{entry.node ?? "الخادم"}</td>
        <td>
          {detail ? (
            <button className="btn ghost" onClick={onToggle}>
              {isOpen ? "إخفاء" : "تفاصيل"}
            </button>
          ) : null}
        </td>
      </tr>
      {isOpen && detail ? (
        <tr>
          <td colSpan={7}>
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
              {JSON.stringify(detail, null, 2)}
            </pre>
            <div className="hint" style={{ fontFamily: "monospace" }}>
              معرّف السجل: {entry.entity_id}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
