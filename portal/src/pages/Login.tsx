import { useState } from "react";
import { useAuth } from "../auth";

export default function Login() {
  const { signIn, error } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await signIn(username.trim(), password);
    } catch {
      /* the error is shown from context */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>المنصة المركزية للمؤشرات الصحية</h1>
        <p className="sub">وزارة الصحة العامة والسكان — الجمهورية اليمنية</p>

        {error ? <div className="error-box">{error}</div> : null}

        <div className="field">
          <label htmlFor="u">اسم المستخدم</label>
          <input
            id="u"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="p">كلمة المرور</label>
          <input
            id="p"
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

        <p className="hint" style={{ marginTop: 16 }}>
          حسابات تجريبية: <code>central.admin</code> (مركزي) · <code>sanaa.gov</code> (محافظة) ·{" "}
          <code>rep.manager</code> (مستشفى) — كلمة المرور <code>Demo@12345</code>
        </p>
      </form>
    </div>
  );
}
