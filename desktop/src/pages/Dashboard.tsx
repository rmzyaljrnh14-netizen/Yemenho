import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Hospital } from "../types";

export default function Dashboard() {
  const { me } = useAuth();
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setHospitals(await api.hospitals());
      } catch (e) {
        setError(e instanceof Error ? e.message : "تعذّر تحميل البيانات.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>لوحة المعلومات</h3>
        <p className="hint">
          هذه اللوحة تعرض البيانات التي يسمح لك نطاق صلاحيتك برؤيتها فقط. عدد المستشفيات
          الظاهرة لك: <b>{hospitals.length}</b>.
        </p>
        <div className="grid-2" style={{ marginTop: 12 }}>
          <div className="card" style={{ marginBottom: 0 }}>
            <div className="hint">مستوى الصلاحية</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>
              {me?.scope_org.level === "central"
                ? "الإدارة المركزية (كل المستشفيات)"
                : me?.scope_org.level === "governorate"
                  ? "مكتب صحة المحافظة"
                  : me?.scope_org.level === "hospital"
                    ? "مستشفى واحد"
                    : "قسم"}
            </div>
          </div>
          <div className="card" style={{ marginBottom: 0 }}>
            <div className="hint">عدد الصلاحيات الممنوحة</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{me?.scopes.length ?? 0}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>المستشفيات ضمن نطاقك</h3>
        {loading ? (
          <div className="empty">جارٍ التحميل...</div>
        ) : error ? (
          <div className="error-box">{error}</div>
        ) : hospitals.length === 0 ? (
          <div className="empty">لا توجد مستشفيات ضمن نطاقك.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>المستشفى</th>
                <th>الرمز</th>
                <th>الحالة</th>
              </tr>
            </thead>
            <tbody>
              {hospitals.map((h) => (
                <tr key={h.id}>
                  <td>{h.name_ar}</td>
                  <td>{h.code}</td>
                  <td>
                    <span className={h.is_active ? "badge ok" : "badge off"}>
                      {h.is_active ? "نشط" : "غير نشط"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
