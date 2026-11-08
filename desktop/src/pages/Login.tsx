import { useState } from "react";
import { useAuth } from "../auth";

export default function Login() {
  const { signIn, error } = useAuth();
  const [username, setUsername] = useState("central.admin");
  const [password, setPassword] = useState("Demo@12345");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await signIn(username, password);
    } catch {
      /* error shown from context */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>النظام الوطني لإدارة مؤشرات الأداء الصحي والجودة وسلامة المرضى</h1>
        <p className="sub">وزارة الصحة العامة والسكان — تسجيل الدخول</p>

        {error && <div className="error-box">{error}</div>}

        <div className="field">
          <label htmlFor="username">اسم المستخدم</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">كلمة المرور</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        <button className="primary" type="submit" disabled={busy} style={{ width: "100%" }}>
          {busy ? "جارٍ الدخول..." : "دخول"}
        </button>

        <p className="hint" style={{ marginTop: 14 }}>
          بيانات تجريبية: <code>central.admin</code> / <code>rep.quality</code> /{" "}
          <code>rep.reader</code> — كلمة المرور <code>Demo@12345</code>
        </p>
      </form>
    </div>
  );
}
