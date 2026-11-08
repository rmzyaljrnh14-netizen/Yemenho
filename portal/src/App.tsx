import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Shell from "./Shell";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Comparisons from "./pages/Comparisons";
import Tracking from "./pages/Tracking";
import Alerts from "./pages/Alerts";
import Hospitals from "./pages/Hospitals";
import Users from "./pages/Users";
import Indicators from "./pages/Indicators";
import Audit from "./pages/Audit";
import SyncMonitor from "./pages/SyncMonitor";

// ECharts is heavy; the chart-bearing pages are loaded on demand so the rest of
// the portal keeps a small initial bundle.
const Charts = lazy(() => import("./pages/Charts"));
const HospitalDetail = lazy(() => import("./pages/HospitalDetail"));
const Quality = lazy(() => import("./pages/Quality"));
const Assistant = lazy(() => import("./pages/Assistant"));

function Protected({ children }: { children: JSX.Element }) {
  const { me, loading } = useAuth();
  if (loading)
    return (
      <div className="login-wrap">
        <div className="login-card">جارٍ التحميل...</div>
      </div>
    );
  if (!me) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const { me, loading } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={loading ? <div /> : me ? <Navigate to="/" replace /> : <Login />} />
      <Route
        path="/"
        element={
          <Protected>
            <Shell />
          </Protected>
        }
      >
        <Route index element={<Dashboard />} />
        <Route
          path="charts"
          element={
            <Suspense fallback={<div className="card">جارٍ تحميل الرسوم البيانية...</div>}>
              <Charts />
            </Suspense>
          }
        />
        <Route path="comparisons" element={<Comparisons />} />
        <Route path="tracking" element={<Tracking />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="hospitals" element={<Hospitals />} />
        <Route
          path="hospital/:hospitalId"
          element={
            <Suspense fallback={<div className="card">جارٍ تحميل تقرير المستشفى...</div>}>
              <HospitalDetail />
            </Suspense>
          }
        />
        <Route path="users" element={<Users />} />
        <Route path="indicators" element={<Indicators />} />
        <Route
          path="quality"
          element={
            <Suspense fallback={<div className="card">جارٍ تحميل وحدات الجودة...</div>}>
              <Quality />
            </Suspense>
          }
        />
        <Route
          path="assistant"
          element={
            <Suspense fallback={<div className="card">جارٍ تحميل المساعد الذكي...</div>}>
              <Assistant />
            </Suspense>
          }
        />
        <Route path="audit" element={<Audit />} />
        <Route path="sync" element={<SyncMonitor />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
