import { Suspense, type ReactNode } from 'react';
import { createBrowserRouter, Navigate } from 'react-router';
import AppLayout from './components/Layout/AppLayout';
import {
  AnalyticsPage,
  BacklogPage,
  CapacityPage,
  DashboardPage,
  PlanningPage,
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
      { index: true, element: page(<DashboardPage />) },
      { path: 'analytics', element: page(<AnalyticsPage />) },
      { path: 'sync', element: page(<SyncPage />) },
      { path: 'scope', element: <Navigate to="/sync" replace /> },
      { path: 'capacity', element: page(<CapacityPage />) },
      { path: 'backlog', element: page(<BacklogPage />) },
      { path: 'planning', element: page(<PlanningPage />) },
    ],
  },
]);
