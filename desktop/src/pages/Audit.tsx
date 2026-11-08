import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { AuditEntry, AuditFacets, AuditLogPage } from "../types";

const PAGE_SIZE = 50;

interface Filters {
  entityType: string;
  action: string;
  actorUserId: string;
  since: string;
  until: string;
  q: string;
}

const EMPTY: Filters = { entityType: "", action: "", actorUserId: "", since: "", until: "", q: "" };

function toParams(f: Filters, offset: number) {
  return {
    entityType: f.entityType || undefined,
    action: f.action || undefined,
    actorUserId: f.actorUserId || undefined,
    since: f.since ? new Date(f.since).toISOString() : undefined,
    until: f.until ? new Date(f.until).toISOString() : undefined,
    q: f.q || undefined,
    limit: PAGE_SIZE,
    offset,
  };
}

export default function Audit() {
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<AuditLogPage | null>(null);
  const [facets, setFacets] = useState<AuditFacets | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .auditLog(toParams(filters, offset))
      .then((d) => {
        if (!cancelled) setPage(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "تعذّر تحميل السجل.");
      });
    return () => {
      cancelled = true;
    };
  }, [filters, offset]);

  useEffect(() => {
    api
      .auditFacets()
      .then(setFacets)
      .catch(() => setFacets(null));
  }, []);

  const entries = page?.entries ?? [];
  const total = page?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = offset + entries.length;

  const entityLabel = useMemo(() => {
    const map = new Map<string, string>();
    (facets?.entity_types ?? []).forEach((f) => map.set(f.code, f.label_ar));
    return map;
  }, [facets]);

  const apply = () => {
    setError(null);
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
    <div className="card">
      <h3 style={{ marginTop: 0 }}>سجل التدقيق</h3>
      <p className="hint">
        كل إجراء حساس يُسجَّل: من قام به، وماذا، ومتى. السجل للقراءة فقط ويقتصر على نطاقك وفق الصلاحيات.
      </p>
      {error && <div className="error-box">{error}</div>}
      {exportError && <div className="error-box">{exportError}</div>}

      <div className="row" style={{ flexWrap: "wrap", gap: 12 }}>
        <div className="field" style={{ flex: "0 0 200px" }}>
          <label htmlFor="f-type">نوع الكيان</label>
          <select id="f-type" value={draft.entityType} onChange={(e) => setDraft({ ...draft, entityType: e.target.value })}>
            <option value="">الكل</option>
            {(facets?.entity_types ?? []).map((f) => (
              <option key={f.code} value={f.code}>
                {f.label_ar} ({f.count})
              </option>
            ))}
          </select>
        </div>

        <div className="field" style={{ flex: "0 0 180px" }}>
          <label htmlFor="f-action">الإجراء</label>
          <select id="f-action" value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })}>
            <option value="">الكل</option>
            {(facets?.actions ?? []).map((f) => (
              <option key={f.code} value={f.code}>
                {f.label_ar} ({f.count})
              </option>
            ))}
          </select>
        </div>

        <div className="field" style={{ flex: "0 0 200px" }}>
          <label htmlFor="f-actor">المستخدم</label>
          <select id="f-actor" value={draft.actorUserId} onChange={(e) => setDraft({ ...draft, actorUserId: e.target.value })}>
            <option value="">الكل</option>
            {(facets?.actors ?? []).map((a) => (
              <option key={a.user_id} value={a.user_id}>
                {a.name} ({a.count})
              </option>
            ))}
          </select>
        </div>

        <div className="field" style={{ flex: "0 0 190px" }}>
          <label htmlFor="f-since">من تاريخ</label>
          <input id="f-since" type="datetime-local" value={draft.since} onChange={(e) => setDraft({ ...draft, since: e.target.value })} />
        </div>

        <div className="field" style={{ flex: "0 0 190px" }}>
          <label htmlFor="f-until">إلى تاريخ</label>
          <input id="f-until" type="datetime-local" value={draft.until} onChange={(e) => setDraft({ ...draft, until: e.target.value })} />
        </div>

        <div className="field" style={{ flex: "0 0 200px" }}>
          <label htmlFor="f-q">بحث</label>
          <input
            id="f-q"
            type="text"
            placeholder="معرّف السجل أو كلمة"
            value={draft.q}
            onChange={(e) => setDraft({ ...draft, q: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Enter") apply();
            }}
          />
        </div>
      </div>

      <div className="row" style={{ gap: 8 }}>
        <button className="primary" onClick={apply}>
          تطبيق
        </button>
        <button onClick={reset}>إعادة تعيين</button>
        <button onClick={() => doExport("xlsx")}>تصدير Excel</button>
        <button onClick={() => doExport("csv")}>تصدير CSV</button>
      </div>

      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <span className="hint">
          المعروض {shownFrom}–{shownTo} من {total}
        </span>
        <span style={{ display: "flex", gap: 8 }}>
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            السابق
          </button>
          <button disabled={shownTo >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
            التالي
          </button>
        </span>
      </div>

      {entries.length === 0 ? (
        <div className="empty">لا توجد سجلات مطابقة.</div>
      ) : (
        <div className="scroll-y">
          <table>
            <thead>
              <tr>
                <th>الوقت</th>
                <th>المستخدم</th>
                <th>الملخّص</th>
                <th>الإجراء</th>
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
      )}
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
          <span className="hint"> ({entityLabel})</span>
        </td>
        <td>
          <span className="badge">{entry.action_label_ar}</span>
        </td>
        <td>
          {detail ? (
            <button onClick={onToggle}>{isOpen ? "إخفاء" : "تفاصيل"}</button>
          ) : null}
        </td>
      </tr>
      {isOpen && detail ? (
        <tr>
          <td colSpan={5}>
            <pre style={{ direction: "ltr", textAlign: "left", fontSize: 12, overflowX: "auto" }}>
              {JSON.stringify(detail, null, 2)}
            </pre>
            <div className="hint">معرّف السجل: {entry.entity_id}</div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
