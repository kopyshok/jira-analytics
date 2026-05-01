import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { Space, DatePicker, Switch, Empty, Spin, Button } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import PageHeader from '../components/shared/PageHeader';
import AnalyticsTeamList from '../components/analytics/AnalyticsTeamList';
import AnalyticsFilters from '../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../components/analytics/AnalyticsTable';
import AnalyticsColumnSettings from '../components/analytics/AnalyticsColumnSettings';
import { useAnalyticsReport } from '../hooks/useAnalyticsReport';
import { useGlobalPeriod } from '../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

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
  const [worklogMode, setWorklogMode] = useState<'inline' | 'drawer'>('inline');
  const [columnSettingsOpen, setColumnSettingsOpen] = useState(false);

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

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader eyebrow="Аналитика" title="Иерархический отчёт по часам" />

      <Space wrap>
        <DatePicker.RangePicker
          value={localRange}
          onChange={setLocalRange}
          placeholder={['Уточнить с', 'по']}
          allowClear
        />
        <span>Ворклоги:</span>
        <Switch
          checkedChildren="inline"
          unCheckedChildren="drawer"
          checked={worklogMode === 'inline'}
          onChange={(v) => setWorklogMode(v ? 'inline' : 'drawer')}
        />
        <Button
          icon={<SettingOutlined />}
          onClick={() => setColumnSettingsOpen(true)}
        >
          Настройка столбцов
        </Button>
      </Space>

      <AnalyticsColumnSettings
        open={columnSettingsOpen}
        onClose={() => setColumnSettingsOpen(false)}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
        <AnalyticsTeamList
          data={data}
          selected={selectedTeam}
          onSelect={setSelectedTeam}
        />
        <div>
          <AnalyticsFilters
            urlParams={{ employeeId, workType, category, taskQ }}
            onChange={(next) => {
              const p = new URLSearchParams(params);
              const set = (k: string, v: string | undefined) => {
                if (v) p.set(k, v); else p.delete(k);
              };
              set('employee', next.employeeId);
              set('work_type', next.workType);
              set('category', next.category);
              set('task', next.taskQ);
              setParams(p);
            }}
          />
          {isLoading ? (
            <Spin />
          ) : !data?.teams.length ? (
            <Empty description="Нет данных за выбранный период" />
          ) : (
            <AnalyticsTable
              data={data}
              selectedTeam={selectedTeam}
              worklogMode={worklogMode}
              periodStart={localRange?.[0]?.format('YYYY-MM-DD') || ''}
              periodEnd={localRange?.[1]?.format('YYYY-MM-DD') || ''}
            />
          )}
        </div>
      </div>
    </Space>
  );
}
