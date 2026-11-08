import { Link, NavLink, Outlet } from "react-router-dom";
import { LEVEL_AR, hasPermission, roleLabel, useAuth } from "./auth";

interface NavItem {
  to: string;
  label: string;
  perm: string | null;
}

const GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "القيادة والمتابعة",
    items: [
      { to: "/", label: "لوحة القيادة الوطنية", perm: null },
      { to: "/charts", label: "الرسوم والمؤشرات الوطنية", perm: "report.view" },
      { to: "/comparisons", label: "المقارنات", perm: "report.view" },
      { to: "/tracking", label: "متابعة التقارير", perm: "report.view" },
      { to: "/alerts", label: "مركز التنبيهات", perm: "report.view" },
    ],
  },
  {
    label: "الجودة وسلامة المرضى",
    items: [
      { to: "/quality", label: "الجودة وسلامة المرضى", perm: "report.view" },
      { to: "/assistant", label: "المساعد الذكي", perm: "assistant.use" },
    ],
  },
  {
    label: "الإدارة",
    items: [
      { to: "/hospitals", label: "المستشفيات والأقسام", perm: null },
      { to: "/indicators", label: "مكتبة المؤشرات الوطنية", perm: "report.view" },
      { to: "/users", label: "المستخدمون والصلاحيات", perm: "user.manage" },
      { to: "/audit", label: "سجل التدقيق", perm: "audit.view" },
      { to: "/sync", label: "مركز المزامنة", perm: "sync.view" },
    ],
  },
];

export default function Shell() {
  const { me, signOut } = useAuth();
  const level = me?.scope_org.level ?? "";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          المنصة المركزية للمؤشرات الصحية
          <small>وزارة الصحة العامة والسكان — الجمهورية اليمنية</small>
        </div>
        <nav className="nav">
          {GROUPS.map((g) => {
            const items = g.items.filter((n) => n.perm === null || hasPermission(me, n.perm));
            if (items.length === 0) return null;
            return (
              <div key={g.label}>
                <div className="group-label">{g.label}</div>
                {items.map((n) => (
                  <NavLink key={n.to} to={n.to} end={n.to === "/"}>
                    {n.label}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>
      </aside>

      <main className="content">
        <div className="topbar">
          <h2>مرحباً، {me?.display_name ?? "..."}</h2>
          <div className="chips">
            <span className="chip">{LEVEL_AR[level] ?? "نطاق غير محدد"}</span>
            {me?.roles.map((r) => (
              <span className="chip" key={r}>
                {roleLabel(r)}
              </span>
            ))}
            <Link
              to="#"
              onClick={(e) => {
                e.preventDefault();
                signOut();
              }}
            >
              <span className="badge off">خروج</span>
            </Link>
          </div>
        </div>
        <Outlet />
      </main>
    </div>
  );
}
