import { Suspense, type ReactNode } from 'react';
import { createBrowserRouter, Navigate } from 'react-router';
import AppLayout from './components/Layout/AppLayout';
import FactFilterProvider from './components/dashboard/FactFilterProvider';
import {
  AnalyticsPage,
  BacklogPage,
  CapacityPage,
  CategoriesEditorPage,
  DashboardPage,
  PlanningPage,
  SettingsPage,
  SyncHubPage,
  SyncPage,
} from './pages/lazyPages';

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

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <FactFilterProvider>{page(<DashboardPage />)}</FactFilterProvider> },
      { path: 'analytics', element: <FactFilterProvider>{page(<AnalyticsPage />)}</FactFilterProvider> },
      { path: 'sync', element: page(<SyncHubPage />) },
      { path: 'sync-old', element: page(<SyncPage />) },
      { path: 'categories', element: page(<CategoriesEditorPage />) },
      { path: 'scope', element: <Navigate to="/sync" replace /> },
      { path: 'capacity', element: page(<CapacityPage />) },
      { path: 'backlog', element: page(<BacklogPage />) },
      { path: 'planning', element: page(<PlanningPage />) },
      { path: 'settings', element: page(<SettingsPage />) },
    ],
  },
]);
