import React, { Suspense, type ReactNode } from 'react';
import { createBrowserRouter, Navigate, Outlet } from 'react-router';
import AppLayout from './components/Layout/AppLayout';
import { AuthProvider } from './components/AuthProvider';
import { GlobalTeamFilterProvider } from './components/GlobalTeamFilterProvider';
import { GlobalPeriodFilterProvider } from './components/shared/GlobalPeriodFilterProvider';
import { useAuth } from './hooks/useAuth';
import {
  AnalyticsPage,
  BacklogPage,
  CapacityPage,
  CategoriesEditorPage,
  DashboardPage,
  ExecutiveDashboardPage,
  FeedbackPage,
  PlanningPage,
  ProjectsPage,
  ResourcePlanningPage,
  ScenarioComparatorPage,
  SettingsPage,
  SyncHubPage,
  WorkTypeReportPage,
  WorkTypeReportPrintPage,
} from './pages/lazyPages';
import LoginPage from './pages/LoginPage';

function page(element: ReactNode) {
  return (
    <Suspense
      fallback={
        <div style={{ minHeight: 240, display: 'grid', placeItems: 'center' }}>
          Загрузка...
        </div>
      }
    >
      {element}
    </Suspense>
  );
}

function AuthLayout() {
  return (
    <AuthProvider>
      <GlobalTeamFilterProvider>
        <GlobalPeriodFilterProvider>
          <Outlet />
        </GlobalPeriodFilterProvider>
      </GlobalTeamFilterProvider>
    </AuthProvider>
  );
}

function ProtectedRoute({ children, adminOnly }: { children: React.ReactNode; adminOnly?: boolean }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== 'admin') return <Navigate to="/" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  {
    element: <AuthLayout />,
    children: [
      {
        path: '/',
        element: <AppLayout />,
        children: [
          { index: true, element: <ProtectedRoute>{page(<DashboardPage />)}</ProtectedRoute> },
          { path: 'projects', element: <ProtectedRoute>{page(<ProjectsPage />)}</ProtectedRoute> },
          { path: 'projects/:key', element: <ProtectedRoute>{page(<ProjectsPage />)}</ProtectedRoute> },
          { path: 'analytics', element: <ProtectedRoute>{page(<AnalyticsPage />)}</ProtectedRoute> },
          { path: 'analytics/work-type-report', element: <ProtectedRoute>{page(<WorkTypeReportPage />)}</ProtectedRoute> },
          { path: 'executive', element: <ProtectedRoute>{page(<ExecutiveDashboardPage />)}</ProtectedRoute> },
          { path: 'sync', element: <ProtectedRoute>{page(<SyncHubPage />)}</ProtectedRoute> },
          { path: 'categories', element: <ProtectedRoute>{page(<CategoriesEditorPage />)}</ProtectedRoute> },
          { path: 'scope', element: <Navigate to="/sync" replace /> },
          { path: 'capacity', element: <ProtectedRoute>{page(<CapacityPage />)}</ProtectedRoute> },
          { path: 'backlog', element: <ProtectedRoute>{page(<BacklogPage />)}</ProtectedRoute> },
          { path: 'planning', element: <ProtectedRoute>{page(<PlanningPage />)}</ProtectedRoute> },
          { path: 'resource-planning', element: <ProtectedRoute>{page(<ResourcePlanningPage />)}</ProtectedRoute> },
          { path: 'resource-planning/compare', element: <ProtectedRoute>{page(<ScenarioComparatorPage />)}</ProtectedRoute> },
          { path: 'settings', element: <ProtectedRoute adminOnly>{page(<SettingsPage />)}</ProtectedRoute> },
          { path: 'feedback', element: <ProtectedRoute>{page(<FeedbackPage />)}</ProtectedRoute> },
        ],
      },
      {
        path: '/analytics/work-type-report/print',
        element: <ProtectedRoute>{page(<WorkTypeReportPrintPage />)}</ProtectedRoute>,
      },
      {
        path: '/login',
        element: <LoginPage />,
      },
    ],
  },
]);
