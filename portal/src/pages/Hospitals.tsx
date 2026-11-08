import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { hasPermission, useAuth } from "../auth";
import { useAsync } from "../lib/useAsync";
import { Card, Empty, ErrorBox, Loading } from "../components/ui";
import type { AssignedIndicator, Department, Hospital, Indicator, Organization } from "../types";

export default function Hospitals() {
  const { me } = useAuth();
  const canOrg = hasPermission(me, "org.manage");
  const canDept = hasPermission(me, "department.manage");

  const hospitals = useAsync<Hospital[]>(useCallback(() => api.hospitals(), []), []);
  const orgs = useAsync<Organization[]>(useCallback(() => api.organizations(), []), []);
  const [selected, setSelected] = useState<Hospital | null>(null);

  useEffect(() => {
    if (!selected && hospitals.data && hospitals.data.length > 0) setSelected(hospitals.data[0]);
  }, [hospitals.data, selected]);

  const govs = useMemo(
    () => (orgs.data ?? []).filter((o) => o.level === "governorate"),
    [orgs.data],
  );

  return (
    <div>
      {hospitals.error ? <ErrorBox message={hospitals.error} /> : null}
      {hospitals.loading && !hospitals.data ? <Loading what="المستشفيات" /> : null}

      <div className="grid-2">
        <Card title={`المستشفيات (${hospitals.data?.length ?? 0})`}>
          {canOrg ? <NewHospitalForm governorates={govs} onDone={hospitals.reload} /> : null}
          {hospitals.data && hospitals.data.length === 0 ? (
            <Empty message="لا توجد مستشفيات ضمن نطاقك." />
          ) : (
            <div className="scroll-y">
              <table>
                <tbody>
                  {hospitals.data?.map((h) => (
                    <tr
                      key={h.id}
                      onClick={() => setSelected(h)}
                      style={{
                        cursor: "pointer",
                        background: selected?.id === h.id ? "#eff6ff" : undefined,
                      }}
                    >
                      <td>{h.name_ar}</td>
                      <td className="hint">{h.code}</td>
                      <td>
                        {h.is_active ? <span className="badge on">نشط</span> : <span className="badge off">موقوف</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div>
          {selected ? (
            <>
              <Card
                title={`الأقسام — ${selected.name_ar}`}
                actions={
                  <Link to={`/hospital/${selected.id}`} className="badge">
                    تقرير المستشفى ←
                  </Link>
                }
              >
                <DepartmentsPanel hospital={selected} canManage={canDept} />
              </Card>
              <Card title="المؤشرات المسندة">
                <AssignmentsPanel hospital={selected} />
              </Card>
            </>
          ) : (
            <Card title="الأقسام">
              <Empty message="اختر مستشفى من القائمة." />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function NewHospitalForm({ governorates, onDone }: { governorates: Organization[]; onDone: () => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [gov, setGov] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createHospital({
        name_ar: name.trim(),
        code: code.trim(),
        governorate_id: gov || null,
        organization_id: gov || null,
      });
      setName("");
      setCode("");
      setGov("");
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذّر إضافة المستشفى.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ marginBottom: 14 }}>
      {error ? <ErrorBox message={error} /> : null}
      <div className="row">
        <div className="field">
          <label>اسم المستشفى</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label>الرمز</label>
          <input value={code} onChange={(e) => setCode(e.target.value)} required placeholder="H-XXX-000" />
        </div>
        <div className="field">
          <label>المحافظة</label>
          <select value={gov} onChange={(e) => setGov(e.target.value)}>
            <option value="">— غير محدد —</option>
            {governorates.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name_ar}
              </option>
            ))}
          </select>
        </div>
        <button className="primary" type="submit" disabled={busy}>
          إضافة مستشفى
        </button>
      </div>
    </form>
  );
}

function DepartmentsPanel({ hospital, canManage }: { hospital: Hospital; canManage: boolean }) {
  const load = useCallback(() => api.departments(hospital.id), [hospital.id]);
  const { data, loading, error, reload } = useAsync<Department[]>(load, [hospital.id]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setAddError(null);
    try {
      await api.createDepartment(hospital.id, { name_ar: name.trim() });
      setName("");
      reload();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "تعذّر إضافة القسم.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error ? <ErrorBox message={error} /> : null}
      {loading && !data ? <Loading what="الأقسام" /> : null}
      {data && data.length === 0 ? <Empty message="لا توجد أقسام بعد." /> : null}
      {data && data.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>القسم</th>
              <th>الرمز</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.id}>
                <td>{d.name_ar}</td>
                <td className="hint">{d.code ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {canManage ? (
        <form className="row" style={{ marginTop: 14 }} onSubmit={submit}>
          {addError ? <ErrorBox message={addError} /> : null}
          <div className="field">
            <label>إضافة قسم</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="مثال: المختبر" />
          </div>
          <button className="primary" type="submit" disabled={busy}>
            إضافة
          </button>
        </form>
      ) : (
        <p className="hint" style={{ marginTop: 12 }}>
          إضافة الأقسام متاحة لمن يملك صلاحية «إدارة الأقسام».
        </p>
      )}
    </>
  );
}

function AssignmentsPanel({ hospital }: { hospital: Hospital }) {
  const load = useCallback(() => api.assignedIndicators(hospital.id), [hospital.id]);
  const { data, loading, error, reload } = useAsync<AssignedIndicator[]>(load, [hospital.id]);
  const library = useAsync<Indicator[]>(useCallback(() => api.indicators(), []), []);
  const [busy, setBusy] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const assignedIds = useMemo(() => new Set((data ?? []).map((a) => a.indicator.id)), [data]);
  const available = useMemo(
    () => (library.data ?? []).filter((i) => !assignedIds.has(i.id)),
    [library.data, assignedIds],
  );
  const [pick, setPick] = useState("");

  async function assign(e: React.FormEvent) {
    e.preventDefault();
    if (!pick) return;
    setBusy(true);
    setAddError(null);
    try {
      await api.assignIndicator(hospital.id, { indicator_id: pick });
      setPick("");
      reload();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "تعذّر إسناد المؤشر.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(assignmentId: string) {
    setBusy(true);
    setAddError(null);
    try {
      await api.unassignIndicator(hospital.id, assignmentId);
      reload();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "تعذّر إلغاء الإسناد.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error ? <ErrorBox message={error} /> : null}
      {loading && !data ? <Loading what="الإسنادات" /> : null}
      {data && data.length === 0 ? <Empty message="لا توجد مؤشرات مسندة لهذا المستشفى." /> : null}
      {data && data.length > 0 ? (
        <div className="scroll-y">
          <table>
            <thead>
              <tr>
                <th>الرمز</th>
                <th>المؤشر</th>
                <th>النطاق</th>
                <th>الهدف</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.assignment_id}>
                  <td>{a.indicator.code}</td>
                  <td>{a.indicator.name_ar}</td>
                  <td>{a.department_id ? "قسم" : "المستشفى"}</td>
                  <td>{a.target_override ?? a.indicator.target_value ?? "—"}</td>
                  <td>
                    <button onClick={() => remove(a.assignment_id)} disabled={busy}>
                      إلغاء
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <form className="row" style={{ marginTop: 14 }} onSubmit={assign}>
        {addError ? <ErrorBox message={addError} /> : null}
        <div className="field" style={{ minWidth: 300 }}>
          <label>إسناد مؤشر من المكتبة الوطنية</label>
          <select value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">— اختر مؤشراً —</option>
            {available.map((i) => (
              <option key={i.id} value={i.id}>
                {i.code} — {i.name_ar}
              </option>
            ))}
          </select>
        </div>
        <button className="primary" type="submit" disabled={busy || !pick}>
          إسناد
        </button>
      </form>
    </>
  );
}
