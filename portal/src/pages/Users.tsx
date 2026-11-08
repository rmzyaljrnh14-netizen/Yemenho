import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { ROLE_AR, useAuth } from "../auth";
import { useAsync } from "../lib/useAsync";
import { Card, Empty, ErrorBox, Loading } from "../components/ui";
import type { Hospital, Organization, UserOut } from "../types";

const SCOPE_TYPES = [
  { value: "central", label: "الإدارة المركزية" },
  { value: "governorate", label: "محافظة" },
  { value: "hospital", label: "مستشفى" },
];

export default function Users() {
  const { me } = useAuth();
  const users = useAsync<UserOut[]>(useCallback(() => api.users(), []), []);
  const orgs = useAsync<Organization[]>(useCallback(() => api.organizations(), []), []);
  const hospitals = useAsync<Hospital[]>(useCallback(() => api.hospitals(), []), []);

  const [selected, setSelected] = useState<UserOut | null>(null);

  const canManage = me?.scopes.includes("user.manage") ?? false;

  return (
    <div>
      {users.error ? <ErrorBox message={users.error} /> : null}
      {users.loading && !users.data ? <Loading what="المستخدمين" /> : null}

      <Card title={`المستخدمون (${users.data?.length ?? 0})`}>
        {canManage ? <NewUserForm onDone={users.reload} /> : null}
        {users.data && users.data.length === 0 ? (
          <Empty message="لا يوجد مستخدمون." />
        ) : (
          <div className="scroll-y">
            <table>
              <thead>
                <tr>
                  <th>اسم المستخدم</th>
                  <th>الاسم الظاهر</th>
                  <th>الحالة</th>
                  <th>أُنشئ في</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {users.data?.map((u) => (
                  <tr
                    key={u.id}
                    style={{ background: selected?.id === u.id ? "#eff6ff" : undefined }}
                  >
                    <td>{u.username}</td>
                    <td>{u.display_name}</td>
                    <td>
                      {u.is_active ? <span className="badge on">نشط</span> : <span className="badge off">موقوف</span>}
                    </td>
                    <td className="hint">{new Date(u.created_at).toLocaleDateString("ar")}</td>
                    <td>
                      <button onClick={() => setSelected(u)}>الأدوار</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selected ? (
        <Card title={`إسناد دور وصلاحية — ${selected.display_name}`}>
          <AssignmentForm
            user={selected}
            governorates={(orgs.data ?? []).filter((o) => o.level === "governorate")}
            hospitals={hospitals.data ?? []}
          />
        </Card>
      ) : null}
    </div>
  );
}

function NewUserForm({ onDone }: { onDone: () => void }) {
  const [username, setUsername] = useState("");
  const [display, setDisplay] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createUser({
        username: username.trim(),
        display_name: display.trim(),
        password,
        email: email.trim() || null,
      });
      setUsername("");
      setDisplay("");
      setPassword("");
      setEmail("");
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذّر إنشاء المستخدم.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ marginBottom: 14 }}>
      {error ? <ErrorBox message={error} /> : null}
      <div className="row">
        <div className="field">
          <label>اسم المستخدم</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="field">
          <label>الاسم الظاهر</label>
          <input value={display} onChange={(e) => setDisplay(e.target.value)} required />
        </div>
        <div className="field">
          <label>البريد (اختياري)</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label>كلمة المرور</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button className="primary" type="submit" disabled={busy}>
          إنشاء مستخدم
        </button>
      </div>
      <p className="hint">كلمة المرور تُخزَّن مُجزَّأة (Argon2) ولا تُحفظ كنص.</p>
    </form>
  );
}

function AssignmentForm({
  user,
  governorates,
  hospitals,
}: {
  user: UserOut;
  governorates: Organization[];
  hospitals: Hospital[];
}) {
  const [role, setRole] = useState("quality_manager");
  const [scopeType, setScopeType] = useState("hospital");
  const [scopeId, setScopeId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const scopeOptions = useMemo(() => {
    if (scopeType === "governorate") return governorates.map((g) => ({ id: g.id, name: g.name_ar }));
    if (scopeType === "hospital") return hospitals.map((h) => ({ id: h.id, name: h.name_ar }));
    return [];
  }, [scopeType, governorates, hospitals]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      await api.createAssignment({
        user_id: user.id,
        role_code: role,
        scope_type: scopeType,
        scope_id: scopeType === "central" ? null : scopeId || null,
      });
      setOk("تم إسناد الدور بنجاح.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذّر إسناد الدور.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      {error ? <ErrorBox message={error} /> : null}
      {ok ? <div className="notice-box">{ok}</div> : null}
      <div className="row">
        <div className="field">
          <label>الدور</label>
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {Object.entries(ROLE_AR).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>نطاق الصلاحية</label>
          <select
            value={scopeType}
            onChange={(e) => {
              setScopeType(e.target.value);
              setScopeId("");
            }}
          >
            {SCOPE_TYPES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        {scopeType !== "central" ? (
          <div className="field">
            <label>{scopeType === "governorate" ? "المحافظة" : "المستشفى"}</label>
            <select value={scopeId} onChange={(e) => setScopeId(e.target.value)} required>
              <option value="">— اختر —</option>
              {scopeOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <button className="primary" type="submit" disabled={busy}>
          إسناد الدور
        </button>
      </div>
      <p className="hint">يُطبَّق عزل البيانات تلقائياً حسب النطاق (RLS على الخادم).</p>
    </form>
  );
}
