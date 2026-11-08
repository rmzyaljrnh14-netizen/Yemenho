import { useEffect, useState } from "react";
import { api } from "../api";
import type { UserOut } from "../types";

export default function Users() {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setUsers(await api.users());
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر التحميل.");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createUser({ username, display_name: displayName, password });
      setUsername("");
      setDisplayName("");
      setPassword("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر إنشاء المستخدم.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>إنشاء مستخدم</h3>
        {error && <div className="error-box">{error}</div>}
        <form className="row" onSubmit={add}>
          <div className="field">
            <label htmlFor="u-name">اسم المستخدم</label>
            <input id="u-name" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="u-display">الاسم الظاهر</label>
            <input id="u-display" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="u-pass">كلمة المرور</label>
            <input
              id="u-pass"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button className="primary" type="submit" disabled={busy}>
            إنشاء
          </button>
        </form>
        <p className="hint">كلمة المرور تُخزَّن مُجزَّأة (Argon2) ولا تُحفظ كنص.</p>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>المستخدمون</h3>
        {users.length === 0 ? (
          <div className="empty">لا يوجد مستخدمون.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>اسم المستخدم</th>
                <th>الاسم الظاهر</th>
                <th>الحالة</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>{u.display_name}</td>
                  <td>
                    <span className={u.is_active ? "badge ok" : "badge off"}>
                      {u.is_active ? "نشط" : "موقوف"}
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
