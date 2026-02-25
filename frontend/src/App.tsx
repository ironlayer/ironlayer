import { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import ErrorBoundary from './components/ErrorBoundary';
import Dashboard from './pages/Dashboard';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';

const PlanDetail = lazy(() => import('./pages/PlanDetail'));
const ModelCatalog = lazy(() => import('./pages/ModelCatalog'));
const ModelDetail = lazy(() => import('./pages/ModelDetail'));
const BackfillPage = lazy(() => import('./pages/BackfillPage'));
const RunDetail = lazy(() => import('./pages/RunDetail'));
const UsageDashboard = lazy(() => import('./pages/UsageDashboard'));
const BillingPage = lazy(() => import('./pages/BillingPage'));
const Environments = lazy(() => import('./pages/Environments'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const AdminDashboard = lazy(() => import('./pages/AdminDashboard'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Suspense
          fallback={
            <div className="flex min-h-screen items-center justify-center bg-surface">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-ironlayer-500/20 border-t-ironlayer-500" role="status" aria-label="Loading page" />
            </div>
          }
        >
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />

            {/* Protected routes */}
            <Route element={<ProtectedRoute />}>
              <Route path="/onboarding" element={<OnboardingPage />} />
              <Route element={<Layout />}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/plans/:id" element={<PlanDetail />} />
                <Route path="/models" element={<ModelCatalog />} />
                <Route path="/models/:name" element={<ModelDetail />} />
                <Route path="/backfills" element={<BackfillPage />} />
                <Route path="/runs/:id" element={<RunDetail />} />
                <Route path="/usage" element={<UsageDashboard />} />
                <Route path="/billing" element={<BillingPage />} />
                <Route path="/environments" element={<Environments />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/admin" element={<AdminDashboard />} />
                <Route path="/admin/reports" element={<ReportsPage />} />
              </Route>
            </Route>
          </Routes>
        </Suspense>
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
