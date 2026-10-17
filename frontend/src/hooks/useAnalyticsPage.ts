import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import type { Dayjs } from 'dayjs';
import analyticsHelp from '../../../docs/help/analytics.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import { useAnalyticsReport } from './useAnalyticsReport';
import { useAnalyticsColumns } from './useAnalyticsColumns';
import { useGlobalPeriod } from './useGlobalPeriod';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';
import { analyticsExportUrl, periodBounds } from '../utils/analyticsTotals';

/**
 * Данные, отбор и действия «Иерархического отчёта по часам» — общие для всех
 * раскладок (Aurora и обложки). Раскладки только рисуют.
 */
export function useAnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const { period } = useGlobalPeriod();
  const { selectedTeams, selectedSubgroups } = useGlobalTeamFilter();

  const [selectedTeam, setSelectedTeam] = useState<string | 'all'>(
    selectedTeams[0] || 'all',
  );

  // URL-driven filters
  const employeeId = params.get('employee') || undefined;
  const workType = params.get('work_type') || undefined;
  const category = params.get('category') || undefined;
  const taskQ = params.get('task') || undefined;

  const [localRange, setLocalRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [worklogMode, setWorklogMode] = useState<'inline' | 'drawer'>('drawer');
  const [hierarchy, setHierarchy] = useState(false);
  const [columnSettingsOpen, setColumnSettingsOpen] = useState(false);
  useRegisterHelp('Аналитика трудозатрат', analyticsHelp);

  const queryParams = useMemo(() => ({
    year: period.year,
    quarter: period.quarter,
    month: period.month,
    start_date: localRange?.[0]?.format('YYYY-MM-DD'),
    end_date: localRange?.[1]?.format('YYYY-MM-DD'),
    teams: selectedTeam !== 'all' ? selectedTeam : (selectedTeams.join(',') || undefined),
    subgroups: selectedSubgroups.join(',') || undefined,
    employee_id: employeeId,
    task_query: taskQ,
    work_type_codes: workType,
    category_codes: category,
    hierarchy,
  }), [period, localRange, selectedTeam, selectedTeams, selectedSubgroups, employeeId, workType, category, taskQ, hierarchy]);

  const { data, isLoading } = useAnalyticsReport(queryParams);
  const { visible: visibleColumns } = useAnalyticsColumns();

  const { start: periodStart, end: periodEnd } = useMemo(() => {
    if (localRange?.[0] && localRange?.[1]) {
      return {
        start: localRange[0].format('YYYY-MM-DD'),
        end: localRange[1].format('YYYY-MM-DD'),
      };
    }
    return periodBounds(period.year, period.quarter, period.month);
  }, [localRange, period]);

  const handleFilterChange = (next: {
    employeeId?: string;
    workType?: string;
    category?: string;
    taskQ?: string;
  }) => {
    const p = new URLSearchParams(params);
    const set = (k: string, v: string | undefined) => {
      if (v) p.set(k, v); else p.delete(k);
    };
    set('employee', next.employeeId);
    set('work_type', next.workType);
    set('category', next.category);
    set('task', next.taskQ);
    setParams(p);
  };

  const hasActiveFilters = Boolean(
    employeeId || workType || category || taskQ || localRange?.[0] || localRange?.[1],
  );

  const resetFilters = () => {
    setLocalRange(null);
    const p = new URLSearchParams(params);
    p.delete('employee');
    p.delete('work_type');
    p.delete('category');
    p.delete('task');
    setParams(p);
  };

  const exportXlsx = () => {
    window.location.href = analyticsExportUrl(import.meta.env.VITE_API_BASE_URL, {
      period, localRange, selectedTeam, selectedTeams, selectedSubgroups,
      employeeId, taskQ, workType, category, visibleColumns, hierarchy,
    });
  };

  return {
    selectedTeam, setSelectedTeam, employeeId, workType, category, taskQ,
    localRange, setLocalRange, worklogMode, setWorklogMode, hierarchy, setHierarchy,
    columnSettingsOpen, setColumnSettingsOpen,
    data, isLoading, periodStart, periodEnd,
    handleFilterChange, hasActiveFilters, resetFilters, exportXlsx,
  };
}

export type AnalyticsPageModel = ReturnType<typeof useAnalyticsPage>;
