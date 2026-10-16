import type { CSSProperties } from 'react';
import { Alert, Badge, Button, Empty, Popover, Segmented, Select, Spin } from 'antd';
import { Lock } from 'lucide-react';
import type { ResourcePlanningPageModel } from '../../../hooks/useResourcePlanningPage';
import { usePlanQuality } from '../../../hooks/useResourcePlanning';
import GanttChart from '../../../components/resource-planning/GanttChart';
import AssignmentSidebar from '../../../components/resource-planning/AssignmentSidebar';
import PlanLoadHeatmap from '../../../components/resource-planning/PlanLoadHeatmap';
import NormedReserveSummary from '../../../components/resource-planning/NormedReserveSummary';
import BulkResetDropdown from '../../../components/resource-planning/BulkResetDropdown';
import RpViewOptions from '../../../components/resource-planning/RpViewOptions';
import type { RpLayout } from '../../../components/resource-planning/GanttRows';
import type { TimelineScale } from '../../../utils/gantt';
import { PHASE_LABELS } from '../../../utils/gantt';
import { splitConflicts } from '../../../utils/rpConflicts';
import { BlockHead, Field, Figure, Figures, PassSection, Passport, SwissData, SwissPage } from '../components/Passport';
import ConflictStrip from './rp/ConflictStrip';
import './resourcePlanning.css';

const LEFT_COL = 340;

const PLAN_STATUS: Record<string, { label: string; tone: string }> = {
  ready: { label: 'Готово', tone: 'is-good' },
  stale: { label: 'Требуется пересчёт', tone: 'is-warn' },
  computing: { label: 'Считается…', tone: 'is-info' },
};

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v)}%`);

function criticalCaption(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'критический конфликт';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'критических конфликта';
  return 'критических конфликтов';
}

/**
 * «Ресурсное планирование» в обложке «Швейцарская»: паспорт (цифры качества
 * плана, выбор плана, действия), справа конфликты, диаграмма с панелью
 * назначения и снизу — загрузка по дням и запас нормированных работ.
 */
export default function SwissResourcePlanningLayout({ vm }: { vm: ResourcePlanningPageModel }) {
  const {
    planId, setPlanId, viewMode, scale, setScale, depDrawMode,
    setBlocksOpen, showRelayArrows, groupBySubgroup, collapsedSections, toggleSection,
    setForkModalOpen, setSelectedAssignmentId, selectedAssignment,
    peopleFilter, setPeopleFilter, peopleOptions, togglePerson, highlightedEmployeeId,
    appearanceSettings, prefs, patchPrefs, layout,
    plansLoading, gantt, ganttLoading, blocks, employees,
    subgroupOrder, subgroupByEmployee, candidateEmployees,
    compute, createPlan, handleCompute, handlePickScenario,
    sortedAssignments, sectionByItem, shownAssignments, shownBookings,
    conflictAssignmentIds, handleToggleCollapse,
    currentScenarioId, scenarioOptions, openCompare,
    createDependency, deleteDependency, onAssignmentChanged,
  } = vm;
  const { data: quality } = usePlanQuality(planId);
  const criticals = gantt
    ? splitConflicts(gantt.conflicts, false).active.filter((c) => c.severity === 'critical').length
    : 0;
  const status = gantt ? PLAN_STATUS[gantt.plan.status] ?? { label: 'Черновик', tone: 'is-muted' } : null;
  const initiatives = new Set(shownAssignments.map((a) => a.backlog_item_id)).size;
  const quarterLabel = gantt ? `${gantt.plan.quarter ?? ''} ${gantt.plan.year ?? ''}`.trim() : '';
  const phases = appearanceSettings.phase_colors;
  const computing = compute.isPending || gantt?.plan.status === 'computing';

  return (
    <SwissPage passportSpan={2} className="sw-rp">
      <Passport eyebrow="2.0 Паспорт экрана" title="Ресурсное планирование">
        <Button block className="sw-rp-blocks" icon={<Lock size={14} strokeWidth={1.5} />} onClick={() => setBlocksOpen(true)}>
          Заблокированные периоды
        </Button>

        <Figures>
          <Figure value={pct(quality?.overload_days_pct)} caption="Перегрузки" title="Доля перегруженных дней" />
          <Figure value={quality?.late_count ?? '—'} caption="Просрочки" />
          <Figure value={pct(quality?.mean_utilization_pct)} caption="Утилизация" title="Среднее использование ёмкости" />
          <Figure
            value={gantt ? criticals : '—'}
            caption={criticalCaption(criticals)}
            tone={criticals > 0 ? 'accent' : undefined}
            strong
          />
        </Figures>

        <PassSection eyebrow="2.1 План">
          <Field label="План">
            <Select
              data-tour="rp-scenario-select"
              variant="underlined"
              loading={plansLoading || createPlan.isPending}
              placeholder="Выберите утверждённый сценарий"
              value={currentScenarioId}
              onChange={handlePickScenario}
              options={scenarioOptions}
              showSearch
              optionFilterProp="label"
              allowClear
              onClear={() => setPlanId(null)}
              popupMatchSelectWidth={360}
            />
          </Field>
          {planId && (
            <Button
              type="primary"
              block
              className="sw-rp-distribute"
              loading={computing}
              onClick={handleCompute}
              data-tour="rp-distribute"
            >
              Распределить
            </Button>
          )}
          {gantt && status && (
            <div className="sw-rp-plan-state">
              <span className={`sw-status ${status.tone}`}><span className="sw-dot" />{status.label}</span>
              {gantt.plan.is_baseline && <span className="sw-chip">Базовый</span>}
              {gantt.plan.label && <span className="sw-chip is-plain" title="Метка копии плана">{gantt.plan.label}</span>}
            </div>
          )}
          {planId && gantt && (
            <div className="sw-linklist">
              <button type="button" className="sw-link-row" onClick={() => setForkModalOpen(true)}>
                Сделать копию плана
              </button>
              <BulkResetDropdown planId={planId} counts={gantt.reset_counts} />
              {gantt.plan.parent_plan_id && (
                <button type="button" className="sw-link-row" onClick={openCompare}>Сравнить с базовым</button>
              )}
            </div>
          )}
        </PassSection>
      </Passport>

      <SwissData
        className="sw-rp-data"
        style={{ '--rp-anim-speed': `${appearanceSettings.animation_speed_seconds}s` } as CSSProperties}
      >
        {gantt?.stale_due_to_other_teams && (
          <Alert
            type="warning"
            showIcon
            className="sw-rp-stale"
            title={`Планы других команд изменились после расчёта${
              gantt.stale_teams?.length ? ` (${gantt.stale_teams.join(', ')})` : ''
            } — нажмите «Распределить»`}
            action={<Button size="small" loading={computing} onClick={handleCompute}>Распределить</Button>}
          />
        )}
        {gantt && viewMode !== 'plane' && (
          <ConflictStrip
            conflicts={gantt.conflicts}
            planId={planId}
            onSelectAssignment={(id) => setSelectedAssignmentId(id)}
          />
        )}

        <div className="sw-rp-mid">
          <section className="sw-block sw-rp-gantt">
            <BlockHead
              num="2.3"
              title="Диаграмма Ганта"
              size="lg"
              meta={gantt ? `${quarterLabel} · ${initiatives} ${initiatives === 1 ? 'инициатива' : initiatives < 5 && initiatives > 1 ? 'инициативы' : 'инициатив'}` : undefined}
            >
              {gantt && (
                <Segmented
                  data-tour="rp-layout-switch"
                  size="small"
                  value={layout}
                  onChange={(v) => patchPrefs({ view_mode: v as RpLayout })}
                  options={[
                    { label: 'Задачи', value: 'tasks' },
                    { label: 'Исполнители', value: 'people' },
                  ]}
                />
              )}
              {gantt && (
                <span className="sw-rp-people">
                  <span className="sw-tool-label">Исполнители:</span>
                  <Select
                    data-tour="rp-people-filter"
                    mode="multiple"
                    size="small"
                    variant="underlined"
                    allowClear
                    placeholder="все"
                    value={peopleFilter}
                    onChange={setPeopleFilter}
                    options={peopleOptions}
                    maxTagCount="responsive"
                    showSearch={{ optionFilterProp: 'label' }}
                    popupMatchSelectWidth={280}
                  />
                </span>
              )}
              <Segmented
                data-tour="rp-scale"
                size="small"
                value={prefs.hide_weekends ? 'day' : scale}
                disabled={prefs.hide_weekends}
                onChange={(v) => setScale(v as TimelineScale)}
                options={[
                  { label: 'День', value: 'day' },
                  { label: 'Неделя', value: 'week' },
                  { label: 'Месяц', value: 'month' },
                ]}
              />
              <Popover trigger="click" placement="bottomRight" content={<RpViewOptions vm={vm} />}>
                <Badge dot={prefs.hide_weekends || depDrawMode || groupBySubgroup} offset={[-2, 2]}>
                  <Button size="small" data-tour="rp-view">Вид</Button>
                </Badge>
              </Popover>
            </BlockHead>

            <div className="sw-rp-gantt-scroll">
              {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
              {!planId && !ganttLoading && (
                <Empty description="Выберите план или создайте его из утверждённого сценария" />
              )}
              {gantt && !ganttLoading && planId && (
                <GanttChart
                  assignments={shownAssignments}
                  blocks={blocks}
                  quarter={gantt.plan.quarter ?? 'Q1'}
                  year={gantt.plan.year ?? new Date().getFullYear()}
                  viewMode={viewMode}
                  showRelayArrows={showRelayArrows}
                  planId={planId}
                  employees={employees}
                  scale={scale}
                  dependencies={gantt.dependencies ?? []}
                  externalBookings={shownBookings}
                  layout={layout}
                  employeeLoad={gantt.employee_load}
                  planTeam={gantt.plan.team}
                  depDrawMode={layout === 'tasks' && depDrawMode}
                  collapsedItemIds={prefs.collapsed_initiative_ids}
                  onToggleCollapse={handleToggleCollapse}
                  conflictAssignmentIds={conflictAssignmentIds}
                  onAssignmentClick={(id) => setSelectedAssignmentId(id)}
                  hideWeekends={prefs.hide_weekends}
                  highlightedEmployeeId={highlightedEmployeeId}
                  selectedEmployeeIds={peopleFilter}
                  sectionByItem={sectionByItem}
                  subgroupByEmployee={subgroupOrder.length > 0 ? subgroupByEmployee : undefined}
                  collapsedSections={collapsedSections}
                  onToggleSection={toggleSection}
                  onEmployeeRowClick={togglePerson}
                  onCreateDependency={createDependency}
                  onDeleteDependency={deleteDependency}
                  leftColWidth={LEFT_COL}
                  fitWeekToWidth
                  compactHeader
                  bookingsCollapsed
                />
              )}
            </div>

            {gantt && (
              <div className="sw-legend sw-rp-legend">
                {(['analyst', 'dev', 'qa', 'opo'] as const).map((p) => (
                  <span key={p}><i style={{ background: phases[p] }} />{PHASE_LABELS[p]}</span>
                ))}
                <span><i className="lg-conflict" />конфликт</span>
                <span><i className="lg-cp" />критический путь (КП)</span>
                <span><i className="lg-pinned" />закреплено вручную</span>
                <span><i className="lg-ooq" />за пределами квартала</span>
                <span><i className="lg-absence" />отпуск</span>
                <span><i className="lg-holiday" />праздник</span>
              </div>
            )}
          </section>

          <section className="sw-block sw-rp-assign" aria-label="Назначение">
            {selectedAssignment ? (
              <>
                <AssignmentSidebar
                  docked
                  open
                  onClose={() => setSelectedAssignmentId(null)}
                  planId={planId ?? ''}
                  assignment={selectedAssignment}
                  allAssignments={sortedAssignments}
                  employees={candidateEmployees}
                  onChanged={onAssignmentChanged}
                />
              </>
            ) : (
              <>
                <BlockHead num="2.4" title="Назначение" />
                <div className="sw-empty">
                  Щёлкните полосу фазы на диаграмме — здесь появятся исполнитель, даты, вовлечённость и расчёт фазы.
                </div>
              </>
            )}
          </section>
        </div>

        {viewMode === 'two-level' && gantt && (
          <div className={`sw-rp-bottom${gantt.reserve && gantt.plan.team ? '' : ' is-single'}`}>
            {gantt.employee_load && gantt.employee_load.length > 0 && (
              <section className="sw-block sw-rp-load" data-tour="rp-load">
                <PlanLoadHeatmap
                  planId={gantt.plan.id}
                  rows={gantt.employee_load}
                  subgroupByEmployee={subgroupOrder.length > 0 ? subgroupByEmployee : undefined}
                  subgroupOrder={subgroupOrder}
                  assignments={gantt.assignments}
                  bookings={gantt.external_bookings ?? []}
                  selectedIds={peopleFilter}
                  onEmployeeClick={togglePerson}
                />
              </section>
            )}
            {gantt.reserve && gantt.plan.team && (
              <section className="sw-block sw-rp-reserve">
                <NormedReserveSummary key={gantt.plan.id} reserve={gantt.reserve} defaultExpanded />
              </section>
            )}
          </div>
        )}
      </SwissData>
    </SwissPage>
  );
}
