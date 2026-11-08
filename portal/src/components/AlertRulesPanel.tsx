// Configurable alert-rule editor (v0.10).
//
// The thresholds that drive the alert centre are data. This panel shows the
// catalogue with each rule's effective value and lets an authorised user change
// the numbers (or switch a kind off). Values are validated and clamped on the
// server, so the editor stays honest: it only ever edits thresholds — it never
// creates an alert.

import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";
import { Card, ErrorBox, Loading } from "./ui";
import type { AlertRule } from "../types";

export default function AlertRulesPanel({ hospitalId }: { hospitalId: string | null }) {
  const load = useCallback(() => api.alertRules(hospitalId), [hospitalId]);
  const catalogue = useAsync(load, [hospitalId]);

  return (
    <Card
      title={catalogue.data?.scope === "hospital" ? "عتبات التنبيه — هذا المستشفى" : "عتبات التنبيه — الافتراضي الوطني"}
      actions={catalogue.data ? <button onClick={catalogue.reload}>تحديث</button> : undefined}
    >
      <div className="notice-box" style={{ marginTop: 0 }}>
        {catalogue.data?.note_ar ??
          "غيّر عتبات التنبيه من هنا. القيم تُدقَّق وتُضبط في الخادم، ولا تُختلق أي تنبيهات."}
      </div>
      {catalogue.error ? <ErrorBox message={catalogue.error} /> : null}
      {catalogue.loading && !catalogue.data ? <Loading what="قواعد التنبيه" /> : null}
      {catalogue.data ? (
        <div className="scroll-y">
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
              {catalogue.data.rules.map((rule) => (
                <RuleRow
                  key={rule.kind}
                  rule={rule}
                  hospitalId={hospitalId}
                  onSaved={catalogue.reload}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
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

  // Re-sync when the server state changes (e.g. after a reset or reload).
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
          {rule.params_spec.length === 0 ? <span className="hint">مفتاح تشغيل/إيقاف فقط</span> : null}
        </div>
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
          {hospitalId === null || rule.hospital_override ? (
            <button onClick={reset} disabled={busy}>
              استرجاع الوطني
            </button>
          ) : null}
        </div>
      </td>
    </tr>
  );
}
