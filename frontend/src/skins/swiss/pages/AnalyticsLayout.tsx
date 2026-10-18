import { useState } from 'react';
import { Button, Checkbox, DatePicker, Empty, Segmented, Spin } from 'antd';
import DetailSheet from '../../../components/common/DetailSheet';
import { Download } from 'lucide-react';
import type { AnalyticsPageModel } from '../../../hooks/useAnalyticsPage';
import { LEVEL_LABELS, useAnalyticsLayout } from '../../../hooks/useAnalyticsLayout';
import AnalyticsTeamList from '../../../components/analytics/AnalyticsTeamList';
import AnalyticsFilters from '../../../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../../../components/analytics/AnalyticsTable';
import AnalyticsReportSettings from '../../../components/analytics/AnalyticsReportSettings';
import AnalyticsIssueDrawer from '../../../components/analytics/AnalyticsIssueDrawer';
import SubgroupFlowLine from '../../../components/common/SubgroupFlowLine';
import { planPercent } from '../../../utils/analyticsTotals';
import { BlockHead, Field, Figure, Figures, PassSection, Passport, SwissData, SwissPage } from '../components/Passport';
import { useKeepInView } from '../useKeepInView';
import './analytics.css';

const hours = (v: number, digits = 1) =>
  v.toLocaleString('ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** «2026-10-01» → «01.10.2026». */
const ddmmyyyy = (iso: string) => iso.split('-').reverse().join('.');

/**
 * «Иерархический отчёт по часам» в обложке «Швейцарская»: паспорт (итоги
 * отчёта крупно, отбор столбиком, настройка и выгрузка), справа команды
 * вкладками, переток и таблица-дерево во всю ширину; карточка задачи —
 * в панели подробностей снизу или справа.
 */
export default function SwissAnalyticsLayout({ vm }: { vm: AnalyticsPageModel }) {
  const {
    selectedTeam, setSelectedTeam, employeeId, workType, category, taskQ,
    localRange, setLocalRange, worklogMode, setWorklogMode, hierarchy, setHierarchy,
    columnSettingsOpen, setColumnSettingsOpen, data, isLoading, periodStart, periodEnd,
    handleFilterChange, hasActiveFilters, resetFilters, exportXlsx,
  } = vm;
  // Открытая задача: в режиме «drawer» карточка открывается в панели подробностей.
  const [issue, setIssue] = useState<{ id: string; key: string } | null>(null);
  const { resolved } = useAnalyticsLayout();
  const totals = data?.grand_totals;
  const pct = totals ? planPercent(totals) : null;
  const levels = resolved.visibleLevels
    .filter((l) => selectedTeam === 'all' || l !== 'team')
    .map((l) => LEVEL_LABELS[l].toLowerCase());
  if (!levels.includes('задача')) levels.push('задача');
  const showIssuePanel = worklogMode === 'drawer';
  const shownIssue = showIssuePanel ? issue : null;
  // Рабочая область ужалась под панель — выбранная строка таблицы остаётся на виду.
  useKeepInView(shownIssue?.id, '.sw-an-table-scroll tr.tree-row-selected');

  return (
    <SwissPage className="sw-an">
      <Passport eyebrow="2.0 Аналитика" title="Иерархический отчёт по часам">
        <Figures className="sw-an-figures">
          <Figure
            size="xl"
            value={totals ? hours(totals.fact_hours) : '—'}
            caption="Σ Часов факт"
          />
          <Figure
            size="m"
            value={totals?.plan_hours != null ? hours(totals.plan_hours, 0) : '—'}
            caption="Σ Часов план"
          />
          <Figure size="m" value={pct == null ? '—' : `${Math.round(pct)}%`} caption="Выполнения" />
          <Figure size="m" value={totals ? totals.employee_count : '—'} caption="Сотрудников" />
          <Figure
            size="m"
            value={totals ? hours(totals.foreign_hours) : '—'}
            caption={totals ? `Чужих часов · ${Math.round(totals.foreign_pct)}%` : 'Чужих часов'}
            tone={totals && totals.foreign_hours > 0 ? 'accent' : undefined}
            strong={!!totals && totals.foreign_hours > 0}
          />
        </Figures>

        <PassSection eyebrow="2.1 Отбор">
          <div className="sw-an-range" data-tour="analytics-period">
            <div className="sw-field-row sw-an-range-labels">
              <div className="sw-field-label">Уточнить с</div>
              <div className="sw-field-label">По</div>
            </div>
            <DatePicker.RangePicker
              variant="underlined"
              value={localRange}
              onChange={setLocalRange}
              placeholder={['весь период', 'весь период']}
              format="DD.MM.YYYY"
              allowClear
            />
          </div>
          <Field label="Ворклоги">
            <Segmented
              block
              value={worklogMode}
              onChange={(v) => setWorklogMode(v as 'inline' | 'drawer')}
              options={[
                { value: 'inline', label: 'inline' },
                { value: 'drawer', label: 'drawer' },
              ]}
            />
          </Field>
          <Field label="Иерархия" className="sw-an-hierarchy">
            <span data-tour="analytics-hierarchy">
              <Checkbox checked={hierarchy} onChange={(e) => setHierarchy(e.target.checked)}>
                <b>{hierarchy ? 'ВКЛ' : 'ВЫКЛ'}</b>
                <span className="sw-an-hint">Задачи деревом до самого верхнего родителя</span>
              </Checkbox>
            </span>
          </Field>
          <div data-tour="analytics-filters">
            <AnalyticsFilters
              variant="stack"
              urlParams={{ employeeId, workType, category, taskQ }}
              onChange={handleFilterChange}
            />
          </div>
          <div className="sw-an-actions">
            <Button onClick={() => setColumnSettingsOpen(true)} data-tour="analytics-settings">
              Настройка отчёта
            </Button>
            <Button type="primary" icon={<Download size={14} strokeWidth={1.75} />} onClick={exportXlsx}>
              Экспорт XLSX
            </Button>
            {hasActiveFilters && (
              <button type="button" className="sw-link" onClick={resetFilters}>Сбросить отбор</button>
            )}
          </div>
        </PassSection>
      </Passport>

      <SwissData className="sw-an-data">
        {isLoading ? (
          <Spin />
        ) : !data?.teams.length ? (
          <Empty description="Нет данных за выбранный период">
            {hasActiveFilters && (
              <Button type="primary" onClick={resetFilters}>Сбросить фильтры</Button>
            )}
          </Empty>
        ) : (
          <>
            <AnalyticsTeamList
              variant="tabs"
              num="2.2"
              data={data}
              selected={selectedTeam}
              onSelect={setSelectedTeam}
            />
            {data.subgroup_flow && data.subgroup_flow.length > 0 && (
              <div className="sw-an-flow">
                {data.subgroup_flow.some((i) => i.out_hours > 0 || i.in_hours > 0) ? (
                  <SubgroupFlowLine items={data.subgroup_flow} />
                ) : (
                  <span className="sw-an-flow-empty">
                    <b>Переток внутри команды</b> — группы часами не обменивались
                  </span>
                )}
              </div>
            )}
            <section className="sw-block sw-an-table">
              <BlockHead num="2.3" title="Часы по иерархии" size="lg" meta={levels.join(' · ')}>
                {showIssuePanel && (
                  <span className="sw-tool-label">щелчок по задаче — карточка с ворклогами в панели</span>
                )}
              </BlockHead>
              <div className="sw-an-table-scroll" data-tour="analytics-table">
                <AnalyticsTable
                  data={data}
                  selectedTeam={selectedTeam}
                  worklogMode={worklogMode}
                  periodStart={periodStart}
                  periodEnd={periodEnd}
                  selectedIssueId={shownIssue?.id ?? null}
                  onIssueOpen={setIssue}
                />
              </div>
            </section>
          </>
        )}
      </SwissData>

      {/* Карточка задачи — в панели подробностей снизу или справа (в Aurora — выезжает справа). */}
      <DetailSheet
        open={!!shownIssue}
        onClose={() => setIssue(null)}
        title={<><span className="sw-sheet-num">2.4</span>Задача</>}
        subtitle={`категория, родитель, соседние задачи и ворклоги за ${ddmmyyyy(periodStart)} – ${ddmmyyyy(periodEnd)}`}
        ariaLabel="Задача"
        className="sw-an-sheet"
      >
        {shownIssue && (
          <AnalyticsIssueDrawer
            docked
            issueId={shownIssue.id}
            issueKey={shownIssue.key}
            periodStart={periodStart}
            periodEnd={periodEnd}
            onClose={() => setIssue(null)}
          />
        )}
      </DetailSheet>

      <AnalyticsReportSettings open={columnSettingsOpen} onClose={() => setColumnSettingsOpen(false)} />
    </SwissPage>
  );
}
