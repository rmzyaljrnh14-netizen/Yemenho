import { useEffect, useState } from "react";
import { api } from "../api";
import type { Organization } from "../types";

const LEVEL_LABEL: Record<string, string> = {
  central: "مركزي",
  governorate: "محافظة",
  district: "مديرية",
  hospital: "مستشفى",
};

export default function Organizations() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [level, setLevel] = useState("governorate");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setOrgs(await api.organizations());
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر التحميل.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createOrganization({ name_ar: name.trim(), level });
      setName("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّرت الإضافة.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>إضافة جهة إدارية</h3>
        {error && <div className="error-box">{error}</div>}
        <form className="row" onSubmit={add}>
          <div className="field">
            <label htmlFor="org-name">الاسم</label>
            <input id="org-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="مثال: محافظة حجة" />
          </div>
          <div className="field" style={{ flex: "0 0 180px" }}>
            <label htmlFor="org-level">المستوى</label>
            <select id="org-level" value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="central">مركزي</option>
              <option value="governorate">محافظة</option>
              <option value="district">مديرية</option>
              <option value="hospital">مستشفى</option>
            </select>
          </div>
          <button className="primary" type="submit" disabled={busy}>
            إضافة
          </button>
        </form>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>الهيكل الإداري</h3>
        {orgs.length === 0 ? (
          <div className="empty">لا توجد جهات بعد.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>الاسم</th>
                <th>المستوى</th>
                <th>الرمز</th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((o) => (
                <tr key={o.id}>
                  <td>{o.name_ar}</td>
                  <td>
                    <span className="badge">{LEVEL_LABEL[o.level] ?? o.level}</span>
                  </td>
                  <td className="hint">{o.code ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
