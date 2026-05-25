import { lazy } from 'react';

export const DashboardPage = lazy(() => import('./DashboardPage'));
export const AnalyticsPage = lazy(() => import('./AnalyticsPage'));
export const SyncHubPage = lazy(() => import('./SyncHubPage'));
export const CategoriesEditorPage = lazy(() => import('./CategoriesEditorPage'));
export const CapacityPage = lazy(() => import('./CapacityPage'));
export const BacklogPage = lazy(() => import('./BacklogPage'));
export const PlanningPage = lazy(() => import('./PlanningPage'));
export const SettingsPage = lazy(() => import('./SettingsPage'));
export const ProjectsPage = lazy(() => import('./ProjectsPage'));
export const ResourcePlanningPage = lazy(() => import('./ResourcePlanningPage'));
export const ScenarioComparatorPage = lazy(() => import('./ScenarioComparatorPage'));
export const WorkTypeReportPage = lazy(() => import('./WorkTypeReportPage'));
export const WorkTypeReportPrintPage = lazy(() => import('./WorkTypeReportPrintPage'));
export const ExecutiveDashboardPage = lazy(() => import('./ExecutiveDashboardPage'));
export const FeedbackPage = lazy(() => import('./FeedbackPage'));
