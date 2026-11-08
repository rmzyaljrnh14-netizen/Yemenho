import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Shell from "./Shell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Hospitals from "./pages/Hospitals";
import Organizations from "./pages/Organizations";
import Users from "./pages/Users";
import Audit from "./pages/Audit";
import Indicators from "./pages/Indicators";
import DataEntry from "./pages/DataEntry";
import SyncSettings from "./pages/SyncSettings";
import Quality from "./pages/Quality";
import Assistant from "./pages/Assistant";
import Alerts from "./pages/Alerts";
import { lazy, Suspense } from "react";

// ECharts is heavy; load the reports/dashboards page (and its charts) on demand
// so the rest of the app keeps a small initial bundle.
const Reports = lazy(() => import("./pages/Reports"));

function Protected({ children }: { children: JSX.Element }) {
  const { me, loading } = useAuth();
  if (loading) return <div className="login-wrap"><div className="login-card">جارٍ التحميل...</div></div>;
  if (!me) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const { me, loading } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={loading ? <div /> : me ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/"
        element={
          <Protected>
            <Shell />
          </Protected>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="indicators" element={<Indicators />} />
        <Route path="entry" element={<DataEntry />} />
        <Route
          path="reports"
          element={
            <Suspense fallback={<div className="card">جارٍ تحميل التقارير...</div>}>
              <Reports />
            </Suspense>
          }
        />
        <Route path="quality" element={<Quality />} />
        <Route path="assistant" element={<Assistant />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="hospitals" element={<Hospitals />} />
        <Route path="organizations" element={<Organizations />} />
        <Route path="users" element={<Users />} />
        <Route path="audit" element={<Audit />} />
        <Route path="sync" element={<SyncSettings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
