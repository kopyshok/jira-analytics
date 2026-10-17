import { Button, DatePicker, Empty, Segmented, Spin, Switch } from 'antd';
import { Download, SlidersHorizontal } from 'lucide-react';
import '../warm-layout.css';
import './AnalyticsLayout.css';
import type { AnalyticsPageState, WorklogMode } from '../../../hooks/useAnalyticsPage';
import AnalyticsTeamList from '../../../components/analytics/AnalyticsTeamList';
import AnalyticsFilters from '../../../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../../../components/analytics/AnalyticsTable';
import AnalyticsReportSettings from '../../../components/analytics/AnalyticsReportSettings';
import AnalyticsKpiTiles from '../../../components/analytics/AnalyticsKpiTiles';
import AnalyticsIssueDrawer from '../../../components/analytics/AnalyticsIssueDrawer';
import SubgroupFlowLine from '../../../components/common/SubgroupFlowLine';

/**
 * «Иерархический отчёт по часам» в скине «Тёплая» (макет C-analytics): шапка
 * одной строкой с уточнением дат, режимом ворклогов, иерархией, настройкой и
 * выгрузкой; сводка одной карточкой (и переток внутри команды, если он есть);
 * команды горизонтальным рядом-переключателем, справа — фильтры; ниже —
 * таблица-дерево с закреплённой шапкой и, по клику на задачу, её карточка
 * справа. Страница помещается в экран, длинное прокручивается внутри блоков.
 * Данные и обработчики — общие с раскладкой Aurora (useAnalyticsPage).
 */
export default function WarmAnalyticsLayout({ state }: { state: AnalyticsPageState }) {
  const {
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
  } = state;
  const hasFlow = (data?.subgroup_flow ?? []).some((f) => f.out_hours > 0 || f.in_hours > 0);

  return (
    <div className="wr-fit anc-page">
      <div className="wr-page-head anc-head">
        <div>
          <div className="wr-eyebrow">Аналитика</div>
          <h1 className="wr-h1">Иерархический отчёт по часам</h1>
        </div>
        <div className="anc-actions">
          {/* Обёртка — чтобы экскурсия подсвечивала оба поля дат, а не только первое. */}
          <span className="anc-range" data-tour="analytics-period">
            <DatePicker.RangePicker
              value={localRange}
              onChange={setLocalRange}
              prefix={<span className="anc-ctl-label">Уточнить с</span>}
              separator={<span className="anc-ctl-label">по</span>}
              placeholder={['дд.мм.гггг', 'дд.мм.гггг']}
              format="DD.MM.YYYY"
              suffixIcon={null}
              allowClear
            />
          </span>
          <span className="anc-ctl">
            <span className="anc-ctl-label">Ворклоги:</span>
            <Segmented
              aria-label="Ворклоги"
              className="anc-seg"
              value={worklogMode}
              onChange={(value) => setWorklogMode(value as WorklogMode)}
              options={[
                { value: 'inline', label: 'inline' },
                { value: 'drawer', label: 'drawer' },
              ]}
            />
          </span>
          <span className="anc-ctl" data-tour="analytics-hierarchy">
            <span className="anc-ctl-label">Иерархия:</span>
            <Switch checked={hierarchy} onChange={setHierarchy} aria-label="Иерархия" />
            <span className="anc-ctl-hint">Задачи деревом до самого верхнего родителя</span>
          </span>
          <span className="anc-ctl">
            <Button
              icon={<SlidersHorizontal size={16} aria-hidden />}
              onClick={() => setColumnSettingsOpen(true)}
              data-tour="analytics-settings"
            >
              Настройка отчёта
            </Button>
            <Button type="primary" icon={<Download size={16} aria-hidden />} onClick={exportXlsx}>
              Экспорт XLSX
            </Button>
          </span>
        </div>
      </div>

      <AnalyticsReportSettings
        open={columnSettingsOpen}
        onClose={() => setColumnSettingsOpen(false)}
      />

      {isLoading || !data?.teams.length ? (
        <section className="wr-card anc-empty">
          {isLoading ? (
            <Spin />
          ) : (
            <Empty description="Нет данных за выбранный период">
              {hasActiveFilters && (
                <Button type="primary" onClick={resetFilters}>
                  Сбросить фильтры
                </Button>
              )}
            </Empty>
          )}
        </section>
      ) : (
        <>
          <div className="anc-summary-row">
            <AnalyticsKpiTiles compact totals={data.grand_totals} />
            {hasFlow && <SubgroupFlowLine compact items={data.subgroup_flow} />}
          </div>

          <div className="anc-teams-row">
            <AnalyticsTeamList
              compact
              data={data}
              selected={selectedTeam}
              onSelect={setSelectedTeam}
            />
            <div data-tour="analytics-filters">
              <AnalyticsFilters
                compact
                urlParams={{ employeeId, workType, category, taskQ }}
                onChange={handleFilterChange}
              />
            </div>
          </div>

          <div className="anc-body">
            <section className="wr-card anc-table-card" aria-label="Отчёт" data-tour="analytics-table">
              <AnalyticsTable
                compact
                data={data}
                selectedTeam={selectedTeam}
                worklogMode={worklogMode}
                periodStart={periodStart}
                periodEnd={periodEnd}
                onOpenIssue={setOpenedIssue}
                openIssueId={openedIssue?.id ?? null}
              />
            </section>
            <AnalyticsIssueDrawer
              docked
              issueId={openedIssue?.id ?? null}
              issueKey={openedIssue?.key ?? null}
              periodStart={periodStart}
              periodEnd={periodEnd}
              onClose={() => setOpenedIssue(null)}
            />
          </div>
        </>
      )}
    </div>
  );
}
