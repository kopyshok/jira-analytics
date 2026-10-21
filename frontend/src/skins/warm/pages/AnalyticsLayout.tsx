import { useEffect } from 'react';
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
import DetailSheet from '../../../components/common/DetailSheet';
import SubgroupFlowLine from '../../../components/common/SubgroupFlowLine';
import { useGlobalTeamFilter } from '../../../hooks/useGlobalTeamFilter';
import { useTeamRegistry } from '../../../hooks/useTeamRegistry';

/** 2026-10-01 → 01.10.2026: подсказка в пустых полях дат — границы выбранного периода. */
const ruDate = (iso: string) => iso.split('-').reverse().join('.');

/**
 * «Иерархический отчёт по часам» в скине «Тёплая» (макет C-analytics): шапка
 * одной строкой с уточнением дат, режимом ворклогов, иерархией, настройкой и
 * выгрузкой; сводка одной карточкой и рядом — переток внутри команды;
 * команды горизонтальным рядом-переключателем, справа — фильтры; ниже —
 * таблица-дерево с закреплённой шапкой во всю ширину; карточка задачи с
 * ворклогами (режим drawer) — в панели подробностей снизу или справа.
 * Страница помещается в экран, длинное прокручивается внутри блоков.
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

  // Переток сервер считает только по выбранным командам с делением на группы — пустая
  // карточка говорит, почему она пустая, а не всегда «не обменивались».
  const { selectedTeams } = useGlobalTeamFilter();
  const { data: registry } = useTeamRegistry();
  const flowTeams = selectedTeam !== 'all' ? [selectedTeam] : selectedTeams;
  const flowEmpty = flowTeams.length === 0
    ? 'Выберите команду — покажем обмен часами между её группами'
    : !registry || registry.some((t) => t.has_subgroups && flowTeams.includes(t.name))
      ? 'Группы команды часами между собой не обменивались'
      : flowTeams.length > 1 ? 'В выбранных командах нет деления на группы' : 'В выбранной команде нет деления на группы';

  // Рабочая область ужалась под панель — выбранная строка таблицы остаётся на виду.
  const openedId = openedIssue?.id;
  useEffect(() => {
    if (!openedId) return;
    const frame = requestAnimationFrame(() =>
      document.querySelector('.anc-table-card tr.anc-row-selected')?.scrollIntoView({ block: 'nearest' }));
    return () => cancelAnimationFrame(frame);
  }, [openedId]);

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
              placeholder={[ruDate(periodStart), ruDate(periodEnd)]}
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
            <SubgroupFlowLine compact items={data.subgroup_flow} emptyText={flowEmpty} />
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
              {worklogMode === 'drawer' && (
                <div className="anc-table-hint">
                  Щелчок по задаче — карточка с категорией и ворклогами откроется в панели
                </div>
              )}
            </section>
          </div>
        </>
      )}

      <DetailSheet
        open={!!openedIssue}
        onClose={() => setOpenedIssue(null)}
        title="Карточка задачи"
        subtitle={`категория, соседние задачи и ворклоги за ${ruDate(periodStart)} – ${ruDate(periodEnd)}`}
        ariaLabel="Карточка задачи"
        className="anc-sheet"
      >
        <AnalyticsIssueDrawer
          docked
          issueId={openedIssue?.id ?? null}
          issueKey={openedIssue?.key ?? null}
          periodStart={periodStart}
          periodEnd={periodEnd}
          onClose={() => setOpenedIssue(null)}
        />
      </DetailSheet>
    </div>
  );
}
