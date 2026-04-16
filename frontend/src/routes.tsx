import { Suspense, type ReactNode } from 'react';
import { createBrowserRouter } from 'react-router';
import { Flex, Spin } from 'antd';
import AppLayout from './components/Layout/AppLayout';
import {
  AnalyticsPage,
  BacklogPage,
  CapacityPage,
  DashboardPage,
  PlanningPage,
  ScopePage,
  SyncPage,
} from './pages/lazyPages';

function page(element: ReactNode) {
  return (
    <Suspense
      fallback={
        <Flex justify="center" align="center" style={{ minHeight: 240 }}>
          <Spin />
        </Flex>
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
      { path: 'scope', element: page(<ScopePage />) },
      { path: 'capacity', element: page(<CapacityPage />) },
      { path: 'backlog', element: page(<BacklogPage />) },
      { path: 'planning', element: page(<PlanningPage />) },
    ],
  },
]);
