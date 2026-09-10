import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './components/AuthContext';
import RequireAuth from './components/RequireAuth';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import NewAssessment from './pages/NewAssessment';
import ObligationsIndex from './pages/ObligationsIndex';
import EvidenceVault from './pages/EvidenceVault';
import ReportsList from './pages/ReportsList';
import ProductDashboard from './pages/ProductDashboard';
import AgentChat from './pages/AgentChat';
import Maintenance from './pages/Maintenance';
import ProductDetailPage from './pages/ProductDetailPage';
import NewAssessmentForProduct from './pages/NewAssessmentForProduct';
import './index.css';

function Root() {
  const [maintenance, setMaintenance] = React.useState<boolean | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    fetch('/maintenance.json', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : { enabled: false }))
      .then((d) => {
        if (!cancelled) setMaintenance(Boolean(d && d.enabled === true));
      })
      .catch(() => {
        if (!cancelled) setMaintenance(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (maintenance === null) return null;
  if (maintenance) return <Maintenance />;

  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route path="/" element={<Dashboard />} />
            {/* Product management */}
            <Route path="/products/new" element={<NewAssessment />} />
            <Route path="/products/:productId" element={<ProductDetailPage />} />
            <Route path="/products/:productId/assessments/new" element={<NewAssessmentForProduct />} />
            {/* Assessment workspace (tabs) */}
            <Route path="/assessments/new" element={<NewAssessment />} />
            <Route path="/assessments/:id" element={<Navigate to="info" replace />} />
            <Route path="/assessments/:id/:tab" element={<ProductDashboard />} />
            <Route path="/obligations" element={<ObligationsIndex />} />
            <Route path="/assess" element={<Navigate to="/" replace />} />
            <Route path="/evidence" element={<EvidenceVault />} />
            <Route path="/reports" element={<ReportsList />} />
            <Route path="/assistant" element={<AgentChat />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
