import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth, hasPermission } from "./auth";
import { useSync } from "./useSync";

const NAV = [
  { to: "/", label: "لوحة المعلومات", perm: null },
  { to: "/indicators", label: "مكتبة المؤشرات", perm: "report.view" },
  { to: "/entry", label: "إدخال بيانات المؤشرات", perm: "report.view" },
  { to: "/reports", label: "التقارير ولوحات المعلومات", perm: "report.view" },
  { to: "/quality", label: "الجودة وسلامة المرضى", perm: "report.view" },
  { to: "/assistant", label: "المساعد الذكي", perm: "assistant.use" },
  { to: "/alerts", label: "مركز التنبيهات", perm: "report.view" },
  { to: "/hospitals", label: "المستشفيات والأقسام", perm: null },
  { to: "/organizations", label: "الهيكل الإداري", perm: "org.manage" },
  { to: "/users", label: "المستخدمون", perm: "user.manage" },
  { to: "/audit", label: "سجل التدقيق", perm: "audit.view" },
  { to: "/sync", label: "المزامنة والنسخ الاحتياطي", perm: null },
];

export default function Shell() {
  const { me, signOut } = useAuth();
  const sync = useSync();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          النظام الوطني للجودة وسلامة المرضى
          <small>وزارة الصحة العامة والسكان</small>
        </div>
        <nav className="nav">
          {NAV.filter((n) => n.perm === null || hasPermission(me, n.perm)).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"}>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="content">
        <div className="topbar">
          <h2>مرحباً، {me?.display_name ?? "..."}</h2>
          <div className="chips">
            {sync.desktop && (
              <Link to="/sync" title="حالة المزامنة">
                <span className={`badge ${!sync.online ? "off" : (sync.status?.pending_count ?? 0) > 0 ? "warn" : "on"}`}>
                  {!sync.online
                    ? "دون إنترنت"
                    : (sync.status?.pending_count ?? 0) > 0
                      ? `معلّق: ${sync.status?.pending_count}`
                      : "مُزامن"}
                </span>
              </Link>
            )}
            <span className="chip">
              {me?.scope_org.level === "central"
                ? "الإدارة المركزية"
                : me?.scope_org.level === "governorate"
                  ? "محافظة"
                  : me?.scope_org.level === "hospital"
                    ? "مستشفى"
                    : "قسم"}
            </span>
            {me?.roles.map((r) => (
              <span className="chip" key={r}>
                {r}
              </span>
            ))}
            <Link to="#" onClick={(e) => { e.preventDefault(); signOut(); }}>
              <span className="badge off">خروج</span>
            </Link>
          </div>
        </div>
        <Outlet />
      </main>
    </div>
  );
}
