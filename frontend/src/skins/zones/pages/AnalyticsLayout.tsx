import { Button, DatePicker, Empty, Segmented, Spin, Switch } from 'antd';
import { Download, SlidersHorizontal } from 'lucide-react';
import './analytics.css';
import AnalyticsFilters from '../../../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../../../components/analytics/AnalyticsTable';
import AnalyticsReportSettings from '../../../components/analytics/AnalyticsReportSettings';
import SubgroupFlowLine from '../../../components/common/SubgroupFlowLine';
import AnalyticsKpiTiles from '../../../components/analytics/AnalyticsKpiTiles';
import type { AnalyticsPageState } from '../../../hooks/useAnalyticsPage';
import ZonesBand, { BandField } from '../ZonesBand';

const fmtHours = (h: number) =>
  h.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/**
 * «Аналитика» в скине «Цветовые зоны»: период, ворклоги, иерархия и выгрузка —
 * в полосе зоны; в теле итоги и переток, ряд команд с отборами и таблица во
 * всю ширину; карточка задачи — в панели подробностей (лист снизу или справа).
 * Экран — в высоту окна, таблица листается внутри.
 */
export default function AnalyticsZonesLayout({ an }: { an: AnalyticsPageState }) {
  const {
    selectedTeam, setSelectedTeam, employeeId, workType, category, taskQ,
    localRange, setLocalRange, worklogMode, setWorklogMode, hierarchy, setHierarchy,
    columnSettingsOpen, setColumnSettingsOpen, data, isLoading, periodStart, periodEnd,
    handleFilterChange, hasActiveFilters, resetFilters, exportXlsx,
  } = an;
  const teams = data?.teams ?? [];
  const grand = data?.grand_totals;
  const hasFlow = !!data?.subgroup_flow?.some((i) => i.out_hours > 0 || i.in_hours > 0);

  return (
    <div className="zn-fit anz">
      <ZonesBand eyebrow="Обзор · Аналитика" title="Иерархический отчёт по часам">
        <div className="zn-band-row zn-band-row-split">
          <div className="zn-band-group">
            {/* RangePicker копирует data-* только на первый input — оборачиваем. */}
            <BandField label="Уточнить с" data-tour="analytics-period">
              <DatePicker.RangePicker
                variant="borderless"
                value={localRange}
                onChange={setLocalRange}
                placeholder={['дата', 'по']}
                allowClear
                format="DD.MM.YYYY"
                style={{ width: 230 }}
              />
            </BandField>
            <BandField label="Ворклоги">
              <Segmented
                size="small"
                value={worklogMode}
                onChange={(v) => setWorklogMode(v as 'inline' | 'drawer')}
                options={[
                  { label: 'inline', value: 'inline' },
                  { label: 'drawer', value: 'drawer' },
                ]}
              />
            </BandField>
            {worklogMode === 'drawer' && (
              <span className="anz-band-hint">щелчок по задаче — карточка с ворклогами</span>
            )}
            <label className="zn-band-switch" data-tour="analytics-hierarchy">
              Иерархия
              <Switch size="small" checked={hierarchy} onChange={setHierarchy} />
              <span className="zn-band-switch-hint">задачи деревом до самого верхнего родителя</span>
            </label>
          </div>
          <div className="zn-band-group zn-band-group-end">
            <Button
              icon={<SlidersHorizontal size={14} strokeWidth={1.6} />}
              onClick={() => setColumnSettingsOpen(true)}
              data-tour="analytics-settings"
            >
              Настройка отчёта
            </Button>
            <Button type="primary" icon={<Download size={14} strokeWidth={1.8} />} onClick={exportXlsx}>
              Экспорт XLSX
            </Button>
          </div>
        </div>
      </ZonesBand>

      <AnalyticsReportSettings
        open={columnSettingsOpen}
        onClose={() => setColumnSettingsOpen(false)}
      />

      {isLoading ? (
        <Spin style={{ display: 'block', margin: '60px auto' }} />
      ) : !data?.teams.length || !grand ? (
        <section className="zn-card anz-empty">
          <Empty description="Нет данных за выбранный период">
            {hasActiveFilters && (
              <Button type="primary" onClick={resetFilters}>
                Сбросить фильтры
              </Button>
            )}
          </Empty>
        </section>
      ) : (
        <>
          <div className="anz-top">
            <section className="zn-card anz-kpi">
              <AnalyticsKpiTiles totals={grand} />
            </section>
            {hasFlow && (
              <section className="zn-card anz-flow">
                <SubgroupFlowLine items={data.subgroup_flow} />
              </section>
            )}
          </div>

          <section className="zn-card anz-filters" aria-label="Отборы">
            <span className="anz-label">Команды</span>
            <div className="anz-teams" role="group" aria-label="Команда">
              <button
                type="button"
                className={`anz-team${selectedTeam === 'all' ? ' is-active' : ''}`}
                aria-pressed={selectedTeam === 'all'}
                onClick={() => setSelectedTeam('all')}
              >
                Все команды <span>{fmtHours(grand.fact_hours)} ч</span>
              </button>
              {teams.map((t) => {
                const key = t.team || '_none_';
                const active = selectedTeam === key;
                return (
                  <button
                    key={key}
                    type="button"
                    className={`anz-team${active ? ' is-active' : ''}`}
                    aria-pressed={active}
                    onClick={() => setSelectedTeam(key)}
                  >
                    {t.team || 'Без команды'} <span>{fmtHours(t.totals.fact_hours)} ч</span>
                  </button>
                );
              })}
            </div>
            <div className="anz-filter-right" data-tour="analytics-filters">
              <AnalyticsFilters
                variant="fields"
                urlParams={{ employeeId, workType, category, taskQ }}
                onChange={handleFilterChange}
              />
            </div>
          </section>

          <AnalyticsTable
            docked
            data={data}
            selectedTeam={selectedTeam}
            worklogMode={worklogMode}
            periodStart={periodStart}
            periodEnd={periodEnd}
          />
        </>
      )}
    </div>
  );
}
