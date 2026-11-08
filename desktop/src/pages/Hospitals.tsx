import { useEffect, useState } from "react";
import { api } from "../api";
import { hasPermission, useAuth } from "../auth";
import type { Department, Hospital } from "../types";

export default function Hospitals() {
  const { me } = useAuth();
  const canManage = hasPermission(me, "department.manage");
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [selected, setSelected] = useState<Hospital | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newDept, setNewDept] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const list = await api.hospitals();
        setHospitals(list);
        if (list.length > 0) setSelected(list[0]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذّر التحميل.");
      }
    })();
  }, []);

  useEffect(() => {
    if (!selected) return;
    (async () => {
      try {
        setDepartments(await api.departments(selected.id));
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل الأقسام.");
      }
    })();
  }, [selected]);

  async function addDepartment(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || !newDept.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createDepartment(selected.id, { name_ar: newDept.trim() });
      setNewDept("");
      setDepartments(await api.departments(selected.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر إضافة القسم.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid-2">
      <div className="card">
        <h3 style={{ marginTop: 0 }}>المستشفيات</h3>
        {error && <div className="error-box">{error}</div>}
        {hospitals.length === 0 ? (
          <div className="empty">لا توجد مستشفيات ضمن نطاقك.</div>
        ) : (
          <table>
            <tbody>
              {hospitals.map((h) => (
                <tr
                  key={h.id}
                  onClick={() => setSelected(h)}
                  style={{
                    cursor: "pointer",
                    background: selected?.id === h.id ? "#ecfdf5" : undefined,
                  }}
                >
                  <td>{h.name_ar}</td>
                  <td className="hint">{h.code}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>
          الأقسام {selected ? `— ${selected.name_ar}` : ""}
        </h3>

        {departments.length === 0 ? (
          <div className="empty">لا توجد أقسام بعد.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>القسم</th>
                <th>الرمز</th>
              </tr>
            </thead>
            <tbody>
              {departments.map((d) => (
                <tr key={d.id}>
                  <td>{d.name_ar}</td>
                  <td className="hint">{d.code ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {canManage && selected && (
          <form className="row" style={{ marginTop: 16 }} onSubmit={addDepartment}>
            <div className="field">
              <label htmlFor="dept">إضافة قسم جديد</label>
              <input
                id="dept"
                value={newDept}
                onChange={(e) => setNewDept(e.target.value)}
                placeholder="مثال: المختبر"
              />
            </div>
            <button className="primary" type="submit" disabled={busy}>
              إضافة
            </button>
          </form>
        )}
        {!canManage && (
          <p className="hint" style={{ marginTop: 12 }}>
            إضافة الأقسام متاحة لمدير المستشفى أو مدير النظام المركزي فقط.
          </p>
        )}
      </div>
    </div>
  );
}
