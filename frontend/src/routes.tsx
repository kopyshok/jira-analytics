import { createBrowserRouter } from 'react-router';
import AppLayout from './components/Layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import AnalyticsPage from './pages/AnalyticsPage';
import SyncPage from './pages/SyncPage';
import ScopePage from './pages/ScopePage';
import CapacityPage from './pages/CapacityPage';
import BacklogPage from './pages/BacklogPage';
import PlanningPage from './pages/PlanningPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'analytics', element: <AnalyticsPage /> },
      { path: 'sync', element: <SyncPage /> },
      { path: 'scope', element: <ScopePage /> },
      { path: 'capacity', element: <CapacityPage /> },
      { path: 'backlog', element: <BacklogPage /> },
      { path: 'planning', element: <PlanningPage /> },
    ],
  },
]);
