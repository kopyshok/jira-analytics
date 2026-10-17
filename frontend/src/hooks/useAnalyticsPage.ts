import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import type { Dayjs } from 'dayjs';
import analyticsHelp from '../../../docs/help/analytics.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import { useAnalyticsReport } from './useAnalyticsReport';
import { useAnalyticsColumns } from './useAnalyticsColumns';
import { useGlobalPeriod } from './useGlobalPeriod';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';
import { analyticsExportParams, periodBounds } from '../utils/analyticsView';

export type WorklogMode = 'inline' | 'drawer';

/** Задача, открытая во встроенной панели раскладки скина. */
export interface OpenedIssue {
  id: string;
  key: string;
}

/**
 * Данные, состояние и обработчики «Иерархического отчёта по часам». Один
 * источник для раскладки Aurora и раскладок скинов: период и уточнение дат,
 * команда, фильтры из адресной строки, режим ворклогов, иерархия, настройка
 * отчёта, выгрузка в XLSX.
 */
export function useAnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const { period } = useGlobalPeriod();
  const { selectedTeams, selectedSubgroups } = useGlobalTeamFilter();

  const [selectedTeam, setSelectedTeam] = useState<string | 'all'>(
    selectedTeams[0] || 'all',
  );

  // Фильтры живут в адресной строке — ссылкой можно поделиться.
  const employeeId = params.get('employee') || undefined;
  const workType = params.get('work_type') || undefined;
  const category = params.get('category') || undefined;
  const taskQ = params.get('task') || undefined;

  const [localRange, setLocalRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [worklogMode, setWorklogMode] = useState<WorklogMode>('drawer');
  const [hierarchy, setHierarchy] = useState(false);
  const [columnSettingsOpen, setColumnSettingsOpen] = useState(false);
  // Встроенная панель задачи скина; шторка Aurora держит открытую задачу сама.
  const [openedIssue, setOpenedIssue] = useState<OpenedIssue | null>(null);
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
    const p = analyticsExportParams({
      period,
      startDate: localRange?.[0]?.format('YYYY-MM-DD'),
      endDate: localRange?.[1]?.format('YYYY-MM-DD'),
      selectedTeam,
      selectedTeams,
      selectedSubgroups,
      employeeId,
      taskQ,
      workType,
      category,
      visibleColumns,
      hierarchy,
    });
    window.location.href = `${import.meta.env.VITE_API_BASE_URL}/analytics/report/export.xlsx?${p.toString()}`;
  };

  return {
    data, isLoading,
    selectedTeam, setSelectedTeam,
    employeeId, workType, category, taskQ, handleFilterChange,
    localRange, setLocalRange, hasActiveFilters, resetFilters,
    worklogMode, setWorklogMode,
    hierarchy, setHierarchy,
    columnSettingsOpen, setColumnSettingsOpen,
    openedIssue, setOpenedIssue,
    periodStart, periodEnd,
    exportXlsx,
  };
}

export type AnalyticsPageState = ReturnType<typeof useAnalyticsPage>;
