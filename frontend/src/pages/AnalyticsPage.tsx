import { useEffect, useState, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { Space, DatePicker, Switch, Empty, Spin, Button, Segmented } from 'antd';
import { SettingOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import PageHeader from '../components/shared/PageHeader';
import HelpDrawer from '../components/shared/HelpDrawer';
import analyticsHelp from '../../../docs/help/analytics.md?raw';
import AnalyticsTeamList from '../components/analytics/AnalyticsTeamList';
import AnalyticsFilters from '../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../components/analytics/AnalyticsTable';
import AnalyticsReportSettings from '../components/analytics/AnalyticsReportSettings';
import AnalyticsDetailWorkspace from '../components/analytics/AnalyticsDetailWorkspace';
import AnalyticsKpiTiles from '../components/analytics/AnalyticsKpiTiles';
import { useAnalyticsReport } from '../hooks/useAnalyticsReport';
import { useAnalyticsColumns } from '../hooks/useAnalyticsColumns';
import { useGlobalPeriod } from '../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

/** Returns ISO date bounds for a quarter (and optionally a specific month). */
function periodBounds(year: number, quarter: number, month?: number): { start: string; end: string } {
  if (month != null) {
    const mm = String(month).padStart(2, '0');
    const lastDay = new Date(year, month, 0).getDate();
    return { start: `${year}-${mm}-01`, end: `${year}-${mm}-${lastDay}` };
  }
  const qStartMonth = (quarter - 1) * 3 + 1;
  const qEndMonth = qStartMonth + 2;
  const lastDay = new Date(year, qEndMonth, 0).getDate();
  return {
    start: `${year}-${String(qStartMonth).padStart(2, '0')}-01`,
    end: `${year}-${String(qEndMonth).padStart(2, '0')}-${lastDay}`,
  };
}

type AnalyticsViewMode = 'classic' | 'detail';

const VIEW_MODE_STORAGE_KEY = 'analytics:view-mode';

export default function AnalyticsPage() {
  const [params, setParams] = useSearchParams();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();

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
  const [columnSettingsOpen, setColumnSettingsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [viewMode, setViewMode] = useState<AnalyticsViewMode>(() => {
    try {
      return localStorage.getItem(VIEW_MODE_STORAGE_KEY) === 'detail' ? 'detail' : 'classic';
    } catch {
      return 'classic';
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode);
    } catch {
      /* localStorage may be unavailable */
    }
  }, [viewMode]);

  const queryParams = useMemo(() => ({
    year: period.year,
    quarter: period.quarter,
    month: period.month,
    start_date: localRange?.[0]?.format('YYYY-MM-DD'),
    end_date: localRange?.[1]?.format('YYYY-MM-DD'),
    teams: selectedTeam !== 'all' ? selectedTeam : (selectedTeams.join(',') || undefined),
    employee_id: employeeId,
    task_query: taskQ,
    work_type_codes: workType,
    category_codes: category,
  }), [period, localRange, selectedTeam, selectedTeams, employeeId, workType, category, taskQ]);

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

  const headerActions = (
    <Space wrap>
      <Segmented
        value={viewMode}
        onChange={(value) => setViewMode(value as AnalyticsViewMode)}
        options={[
          { label: 'Текущий вид', value: 'classic' },
          { label: 'Новый вид', value: 'detail' },
        ]}
      />
      <DatePicker.RangePicker
        value={localRange}
        onChange={setLocalRange}
        placeholder={['Уточнить с', 'по']}
        allowClear
      />
      {viewMode === 'classic' && (
        <>
          <span>Ворклоги:</span>
          <Switch
            checkedChildren="inline"
            unCheckedChildren="drawer"
            checked={worklogMode === 'inline'}
            onChange={(v) => setWorklogMode(v ? 'inline' : 'drawer')}
          />
        </>
      )}
      <Button
        icon={<SettingOutlined />}
        onClick={() => setColumnSettingsOpen(true)}
      >
        Настройка отчёта
      </Button>
      <Button
        type="text"
        icon={<QuestionCircleOutlined />}
        onClick={() => setHelpOpen(true)}
        title="Справка по разделу"
      >
        Справка
      </Button>
      <Button
        onClick={() => {
          const p = new URLSearchParams({
            year: String(period.year),
            quarter: String(period.quarter),
            ...(period.month != null ? { month: String(period.month) } : {}),
            ...(localRange?.[0] ? { start_date: localRange[0].format('YYYY-MM-DD') } : {}),
            ...(localRange?.[1] ? { end_date: localRange[1].format('YYYY-MM-DD') } : {}),
            ...(selectedTeam !== 'all' ? { teams: selectedTeam } : selectedTeams.length ? { teams: selectedTeams.join(',') } : {}),
            ...(employeeId ? { employee_id: employeeId } : {}),
            ...(taskQ ? { task_query: taskQ } : {}),
            ...(workType ? { work_type_codes: workType } : {}),
            ...(category ? { category_codes: category } : {}),
            ...(visibleColumns.length ? { columns: visibleColumns.join(',') } : {}),
          });
          window.location.href = `${import.meta.env.VITE_API_BASE_URL}/analytics/report/export.xlsx?${p.toString()}`;
        }}
      >
        Экспорт XLSX
      </Button>
    </Space>
  );

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <PageHeader
        eyebrow="Аналитика"
        title="Иерархический отчёт по часам"
        actions={headerActions}
      />

      <HelpDrawer
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title="Аналитика трудозатрат"
        content={analyticsHelp}
        imageBase="/help-assets/"
      />

      <AnalyticsReportSettings
        open={columnSettingsOpen}
        onClose={() => setColumnSettingsOpen(false)}
      />

      {isLoading ? (
        <Spin />
      ) : !data?.teams.length ? (
        <Empty description="Нет данных за выбранный период">
          {hasActiveFilters && (
            <Button type="primary" onClick={resetFilters}>
              Сбросить фильтры
            </Button>
          )}
        </Empty>
      ) : viewMode === 'detail' ? (
        <AnalyticsDetailWorkspace
          data={data}
          selectedTeam={selectedTeam}
          onSelectTeam={setSelectedTeam}
          urlParams={{ employeeId, workType, category, taskQ }}
          onFilterChange={handleFilterChange}
          periodStart={periodStart}
          periodEnd={periodEnd}
          onOpenColumnSettings={() => setColumnSettingsOpen(true)}
        />
      ) : (
        <>
          <AnalyticsKpiTiles totals={data.grand_totals} />
          <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
          <AnalyticsTeamList
            data={data}
            selected={selectedTeam}
            onSelect={setSelectedTeam}
          />
          <div>
            <AnalyticsFilters
              urlParams={{ employeeId, workType, category, taskQ }}
              onChange={handleFilterChange}
            />
            <AnalyticsTable
              data={data}
              selectedTeam={selectedTeam}
              worklogMode={worklogMode}
              periodStart={periodStart}
              periodEnd={periodEnd}
            />
          </div>
        </div>
        </>
      )}
    </Space>
  );
}
