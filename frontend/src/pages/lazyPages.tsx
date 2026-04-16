import { lazy } from 'react';

export const DashboardPage = lazy(() => import('./DashboardPage'));
export const AnalyticsPage = lazy(() => import('./AnalyticsPage'));
export const SyncPage = lazy(() => import('./SyncPage'));
export const CapacityPage = lazy(() => import('./CapacityPage'));
export const BacklogPage = lazy(() => import('./BacklogPage'));
export const PlanningPage = lazy(() => import('./PlanningPage'));
