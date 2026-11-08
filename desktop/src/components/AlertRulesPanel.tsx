// Configurable alert-rule editor (v0.10) for the desktop app.
//
// The thresholds that drive the alert centre are data on the central server.
// This panel shows the catalogue with each rule's effective value and lets an
// authorised user change the numbers or switch a kind off. Values are validated
// and clamped on the server, so the editor only ever edits thresholds — it never
// creates an alert. Reading or writing the rules needs the network.

import { useEffect, useState } from "react";
import { api } from "../api";
import { useAsync } from "../useAsync";
import type { AlertRule } from "../types";

export default function AlertRulesPanel({ hospitalId }: { hospitalId: string | null }) {
  const load = useAsync(
    () => api.alertRules(hospitalId),
    [hospitalId],
  );

  return (
    <div className="card">
      <div className="row">
        <h3>
          عتبات التنبيه —{" "}
          {load.data?.scope === "hospital" ? "هذا المستشفى" : "الافتراضي الوطني"}
        </h3>
        <button onClick={load.reload}>تحديث</button>
      </div>
      <div className="hint">
        {load.data?.note_ar ??
          "غيّر عتبات التنبيه من هنا. القيم تُدقَّق وتُضبط في الخادم، ولا تُختلق أي تنبيهات."}
      </div>

      {load.loading && !load.data ? <div className="empty">جارٍ جلب قواعد التنبيه...</div> : null}
      {load.error ? (
        <div className="error-box">
          تعذّر جلب قواعد التنبيه من الخادم المركزي. تحتاج هذه الشاشة إلى اتصال بالشبكة.
        </div>
      ) : null}

      {load.data ? (
        <table>
          <thead>
            <tr>
              <th>النوع</th>
              <th>الوصف</th>
              <th>مُفعَّل</th>
              <th>القيم</th>
              <th>النطاق</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {load.data.rules.map((rule) => (
              <RuleRow key={rule.kind} rule={rule} hospitalId={hospitalId} onSaved={load.reload} />
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

function RuleRow({
  rule,
  hospitalId,
  onSaved,
}: {
  rule: AlertRule;
  hospitalId: string | null;
  onSaved: () => void;
}) {
  const [enabled, setEnabled] = useState(rule.enabled);
  const [draft, setDraft] = useState<Record<string, number>>({ ...rule.effective_params });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setEnabled(rule.enabled);
    setDraft({ ...rule.effective_params });
  }, [rule]);

  const dirty =
    enabled !== rule.enabled ||
    rule.params_spec.some((s) => Number(draft[s.key]) !== Number(rule.effective_params[s.key]));

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const params: Record<string, number> = {};
      for (const s of rule.params_spec) params[s.key] = Number(draft[s.key]);
      await api.updateAlertRule(rule.kind, { params, is_enabled: enabled }, hospitalId);
      setSaved(true);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر الحفظ.");
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api.resetAlertRule(rule.kind, hospitalId);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر الاسترجاع.");
    } finally {
      setBusy(false);
    }
  };

  const scopeLabel = rule.hospital_override
    ? "مخصّص للمستشفى"
    : rule.applies_to === "national"
      ? "وطني فقط"
      : "وراثة الوطني";

  return (
    <tr>
      <td>{rule.label_ar}</td>
      <td className="hint">{rule.description_ar}</td>
      <td>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          aria-label={`تفعيل ${rule.label_ar}`}
        />
      </td>
      <td>
        {rule.params_spec.length === 0 ? (
          <span className="hint">مفتاح تشغيل/إيقاف فقط</span>
        ) : (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {rule.params_spec.map((s) => (
              <label key={s.key} style={{ display: "flex", flexDirection: "column", fontSize: 12 }}>
                {s.label_ar}
                {s.unit_ar ? ` (${s.unit_ar})` : ""}
                <input
                  type="number"
                  min={s.min}
                  max={s.max}
                  step={s.step}
                  value={draft[s.key] ?? ""}
                  onChange={(e) => setDraft({ ...draft, [s.key]: Number(e.target.value) })}
                  style={{ width: 110 }}
                />
              </label>
            ))}
          </div>
        )}
        {error ? <div style={{ color: "#b91c1c", marginTop: 4 }}>{error}</div> : null}
        {saved ? <div className="hint" style={{ marginTop: 4 }}>تم الحفظ ✓</div> : null}
      </td>
      <td>
        <span className={rule.hospital_override ? "badge warn" : "badge"}>{scopeLabel}</span>
      </td>
      <td>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button onClick={save} disabled={busy || !dirty}>
            حفظ
          </button>
          {rule.hospital_override ? (
            <button onClick={reset} disabled={busy}>
              استرجاع الوطني
            </button>
          ) : null}
        </div>
      </td>
    </tr>
  );
}
