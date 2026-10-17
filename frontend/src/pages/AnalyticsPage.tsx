import { Space, DatePicker, Switch, Empty, Spin, Button, Tooltip } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import AnalyticsTeamList from '../components/analytics/AnalyticsTeamList';
import AnalyticsFilters from '../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../components/analytics/AnalyticsTable';
import AnalyticsReportSettings from '../components/analytics/AnalyticsReportSettings';
import SubgroupFlowLine from '../components/common/SubgroupFlowLine';
import AnalyticsKpiTiles from '../components/analytics/AnalyticsKpiTiles';
import { useSkin } from '../contexts/ThemeContext';
import { useAnalyticsPage, type AnalyticsPageState } from '../hooks/useAnalyticsPage';
import WarmAnalyticsLayout from '../skins/warm/pages/AnalyticsLayout';

export default function AnalyticsPage() {
  const state = useAnalyticsPage();
  const skin = useSkin();
  if (skin === 'warm') return <WarmAnalyticsLayout state={state} />;
  return <AuroraAnalyticsLayout state={state} />;
}

/** Раскладка Aurora (тёмная и светлая) — как была до выделения данных в хук. */
function AuroraAnalyticsLayout({ state }: { state: AnalyticsPageState }) {
  const {
    data, isLoading,
    selectedTeam, setSelectedTeam,
    employeeId, workType, category, taskQ, handleFilterChange,
    localRange, setLocalRange, hasActiveFilters, resetFilters,
    worklogMode, setWorklogMode,
    hierarchy, setHierarchy,
    columnSettingsOpen, setColumnSettingsOpen,
    periodStart, periodEnd,
    exportXlsx,
  } = state;

  const headerActions = (
    <Space wrap>
      {/* RangePicker копирует data-* только на первый input — оборачиваем, чтобы
          экскурсия подсвечивала весь виджет, а не только поле «с». */}
      <span data-tour="analytics-period" style={{ display: 'inline-flex' }}>
        <DatePicker.RangePicker
          value={localRange}
          onChange={setLocalRange}
          placeholder={['Уточнить с', 'по']}
          allowClear
        />
      </span>
      <span>Ворклоги:</span>
      <Switch
        checkedChildren="inline"
        unCheckedChildren="drawer"
        checked={worklogMode === 'inline'}
        onChange={(v) => setWorklogMode(v ? 'inline' : 'drawer')}
      />
      <Tooltip title="Задачи деревом до самого верхнего родителя">
        <Space size={4} data-tour="analytics-hierarchy">
          <span>Иерархия:</span>
          <Switch checked={hierarchy} onChange={setHierarchy} />
        </Space>
      </Tooltip>
      <Button
        icon={<SettingOutlined />}
        onClick={() => setColumnSettingsOpen(true)}
        data-tour="analytics-settings"
      >
        Настройка отчёта
      </Button>
      <Button onClick={exportXlsx}>
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
      ) : (
        <>
          <AnalyticsKpiTiles totals={data.grand_totals} />
          {data.subgroup_flow && data.subgroup_flow.length > 0 && (
            <div style={{ margin: '4px 0 12px' }}>
              <SubgroupFlowLine items={data.subgroup_flow} />
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
            <AnalyticsTeamList
              data={data}
              selected={selectedTeam}
              onSelect={setSelectedTeam}
            />
            <div>
              <div data-tour="analytics-filters">
                <AnalyticsFilters
                  urlParams={{ employeeId, workType, category, taskQ }}
                  onChange={handleFilterChange}
                />
              </div>
              <div data-tour="analytics-table">
                <AnalyticsTable
                  data={data}
                  selectedTeam={selectedTeam}
                  worklogMode={worklogMode}
                  periodStart={periodStart}
                  periodEnd={periodEnd}
                />
              </div>
            </div>
          </div>
        </>
      )}
    </Space>
  );
}
