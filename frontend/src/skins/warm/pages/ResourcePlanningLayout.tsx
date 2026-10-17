import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Alert, Badge, Button, Empty, Popover, Segmented, Select, Spin } from 'antd';
import { CalculatorOutlined, CheckOutlined, ControlOutlined, LockOutlined } from '@ant-design/icons';
import '../../../utils/gantt.css';
import '../warm-layout.css';
import './ResourcePlanningLayout.css';
import PlanQualityBadge from '../../../components/resource-planning/PlanQualityBadge';
import GanttChart from '../../../components/resource-planning/GanttChart';
import AssignmentSidebar from '../../../components/resource-planning/AssignmentSidebar';
import PlanLoadHeatmap from '../../../components/resource-planning/PlanLoadHeatmap';
import NormedReserveSummary from '../../../components/resource-planning/NormedReserveSummary';
import BulkResetDropdown from '../../../components/resource-planning/BulkResetDropdown';
import RpViewOptions from '../../../components/resource-planning/RpViewOptions';
import RpPageModals from '../../../components/resource-planning/RpPageModals';
import type { RpLayout } from '../../../components/resource-planning/GanttRows';
import { invalidatePlanGantt } from '../../../hooks/useResourcePlanning';
import { planStatusTag, type ResourcePlanningPageState } from '../../../hooks/useResourcePlanningPage';
import { useAppearanceSettings } from '../../../contexts/AppearanceContext';
import type { TimelineScale } from '../../../utils/gantt';
import ConflictStrip from '../components/ConflictStrip';

/** Легенда диаграммы под шкалой: фазы и обозначения полос. */
function GanttLegend() {
  const phase = (key: string, label: string) => (
    <span key={key} className="wr-legend-item">
      <span className="wr-legend-sq" style={{ background: `var(--rp-phase-${key})` }} />
      {label}
    </span>
  );
  return (
    <div className="wr-gantt-legend">
      {phase('analyst', 'Анализ')}
      {phase('dev', 'Разработка')}
      {phase('qa', 'Тестирование')}
      {phase('opo', 'ОПЭ')}
      <span className="wr-legend-item"><span className="wr-legend-bar is-conflict" />конфликт</span>
      <span className="wr-legend-item"><span className="wr-legend-bar is-cp" />критический путь (КП)</span>
      <span className="wr-legend-item"><span className="wr-legend-bar is-pinned" />закреплено вручную</span>
      <span className="wr-legend-item"><span className="wr-legend-hatch is-ooq" />за пределами квартала</span>
      <span className="wr-legend-item"><span className="wr-legend-hatch is-absence" />отпуск</span>
      <span className="wr-legend-item"><span className="wr-legend-hatch is-busy" />занят в другой команде</span>
    </div>
  );
}

/**
 * «Ресурсное планирование» в скине «Тёплая» (макет C-resource): панель плана,
 * конфликты, диаграмма Ганта с встроенной панелью назначения справа (без
 * выбранной фазы — подсказка), внизу — загрузка по дням и запас нормированных
 * работ (оба блока есть всегда, без данных — со спокойной подписью). Страница помещается в экран,
 * длинные части прокручиваются внутри своих блоков. Данные и обработчики —
 * общие с раскладкой Aurora (useResourcePlanningPage).
 */
export default function WarmResourcePlanningLayout({ state }: { state: ResourcePlanningPageState }) {
  const {
    planId, viewMode, scale, setScale, depDrawMode, groupBySubgroup, setBlocksOpen,
    showRelayArrows, collapsedSections, toggleSection, setForkModalOpen,
    selectedAssignment, setSelectedAssignmentId,
    peopleFilter, setPeopleFilter, peopleOptions, togglePerson, highlightedEmployeeId,
    prefs, patchPrefs, layout, plansLoading, gantt, ganttLoading, blocks, employees,
    subgroupOrder, subgroupByEmployee, sectionByItem, candidateEmployees,
    compute, createPlan, handleCompute, handlePickScenario,
    sortedAssignments, shownAssignments, shownBookings, conflictAssignmentIds,
    handleToggleCollapse, createDependency, deleteDependency,
    currentScenarioId, scenarioOptions, setPlanId,
  } = state;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const appearanceSettings = useAppearanceSettings();
  const status = gantt ? planStatusTag(gantt.plan.status) : null;
  const twoLevel = viewMode === 'two-level';

  return (
    <div className="wr-fit wr-rp" style={{ '--rp-anim-speed': `${appearanceSettings.animation_speed_seconds}s` } as React.CSSProperties}>
      <div className="wr-page-head">
        <h1 className="wr-h1">Ресурсное планирование</h1>
        <Button icon={<LockOutlined />} onClick={() => setBlocksOpen(true)}>
          Заблокированные периоды
        </Button>
      </div>

      <section className="wr-card wr-rp-toolbar" aria-label="Управление планом">
        <div className="wr-row">
          <div className="wr-field">
            <label className="wr-field-label" htmlFor="wr-rp-plan">План</label>
            <Select
              id="wr-rp-plan"
              data-tour="rp-scenario-select"
              variant="borderless"
              loading={plansLoading || createPlan.isPending}
              placeholder="Выберите утверждённый сценарий"
              value={currentScenarioId}
              onChange={handlePickScenario}
              options={scenarioOptions}
              style={{ minWidth: 240, maxWidth: 380 }}
              popupMatchSelectWidth={false}
              showSearch
              optionFilterProp="label"
              allowClear
              onClear={() => setPlanId(null)}
            />
          </div>
          {planId && (
            <Button
              icon={<CalculatorOutlined />}
              type="primary"
              loading={compute.isPending || gantt?.plan.status === 'computing'}
              onClick={handleCompute}
              data-tour="rp-distribute"
            >
              Распределить
            </Button>
          )}
          {status && (
            <span className={`wr-pill ${gantt?.plan.status === 'ready' ? 'is-good' : gantt?.plan.status === 'stale' ? 'is-warn' : 'is-neutral'}`}>
              {gantt?.plan.status === 'ready' && <CheckOutlined aria-hidden />}
              {status.label}
            </span>
          )}
          {gantt?.plan.label && <span className="wr-pill is-violet">{gantt.plan.label}</span>}
          {gantt?.plan.is_baseline && <span className="wr-pill is-neutral">Базовый</span>}
          {planId && gantt && <span className="wr-vsep" aria-hidden />}
          {planId && gantt && (
            <Button onClick={() => setForkModalOpen(true)}>Сделать копию плана</Button>
          )}
          {planId && gantt && <BulkResetDropdown planId={planId} counts={gantt.reset_counts} />}
          {gantt?.plan.parent_plan_id && (
            <Button onClick={() => navigate(`/resource-planning/compare?base=${gantt.plan.parent_plan_id}&scen=${planId}`)}>
              Сравнить с базовым
            </Button>
          )}
        </div>
        <div className="wr-row wr-row-between">
          <div className="wr-row">
            {planId && <span className="wr-field-label">Качество плана</span>}
            <PlanQualityBadge planId={planId} />
          </div>
          <div className="wr-row">
            {twoLevel && gantt && (
              <Segmented
                data-tour="rp-layout-switch"
                value={layout}
                onChange={v => patchPrefs({ view_mode: v as RpLayout })}
                options={[
                  { label: 'Задачи', value: 'tasks' },
                  { label: 'Исполнители', value: 'people' },
                ]}
              />
            )}
            {twoLevel && gantt && (
              <Select
                data-tour="rp-people-filter"
                mode="multiple"
                allowClear
                prefix={<span className="wr-field-label">Исполнители</span>}
                placeholder="все"
                value={peopleFilter}
                onChange={setPeopleFilter}
                options={peopleOptions}
                maxTagCount="responsive"
                showSearch={{ optionFilterProp: 'label' }}
                style={{ width: 240 }}
              />
            )}
            {twoLevel && (
              <Segmented
                data-tour="rp-scale"
                value={prefs.hide_weekends ? 'day' : scale}
                disabled={prefs.hide_weekends}
                onChange={v => setScale(v as TimelineScale)}
                options={[
                  { label: 'День', value: 'day' },
                  { label: 'Неделя', value: 'week' },
                  { label: 'Месяц', value: 'month' },
                ]}
              />
            )}
            <Popover trigger="click" placement="bottomRight" content={<RpViewOptions state={state} />}>
              <Badge dot={prefs.hide_weekends || depDrawMode || groupBySubgroup} offset={[-2, 2]}>
                <Button icon={<ControlOutlined />} data-tour="rp-view">Вид</Button>
              </Badge>
            </Popover>
          </div>
        </div>
      </section>

      {gantt?.stale_due_to_other_teams && (
        <Alert
          type="warning"
          showIcon
          title={`Планы других команд изменились после расчёта${
            gantt.stale_teams?.length ? ` (${gantt.stale_teams.join(', ')})` : ''
          } — нажмите «Распределить»`}
          action={
            <Button size="small" loading={compute.isPending || gantt.plan.status === 'computing'} onClick={handleCompute}>
              Распределить
            </Button>
          }
        />
      )}

      {gantt && viewMode !== 'plane' && (
        <ConflictStrip
          conflicts={gantt.conflicts}
          planId={planId}
          onSelectAssignment={(id) => setSelectedAssignmentId(id)}
        />
      )}

      <div className="wr-rp-mid">
        <section className="wr-card wr-rp-gantt" aria-label="Диаграмма Ганта">
          <div className="wr-rp-gantt-scroll">
            {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
            {!planId && !ganttLoading && (
              <Empty style={{ margin: '80px auto' }} description="Выберите план или создайте его из утверждённого сценария" />
            )}
            {gantt && !ganttLoading && planId && viewMode !== 'plane' && (
              <GanttChart
                variant="compact"
                title={<h2 className="rpc-card-title">Диаграмма Ганта</h2>}
                selectedAssignmentId={selectedAssignment?.id ?? null}
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
              />
            )}
          </div>
          {gantt && !ganttLoading && <GanttLegend />}
        </section>

        {!selectedAssignment && gantt && twoLevel && !ganttLoading && (
          <aside className="wr-card wr-rp-assign wr-rp-assign-empty" aria-label="Назначение">
            <h2 className="rpc-card-title">Назначение</h2>
            <p className="wr-rp-empty-text">
              Выберите фазу на диаграмме — здесь можно поменять исполнителя, часы,
              даты и вовлечённость.
            </p>
          </aside>
        )}
        {selectedAssignment && (
          <div className="wr-card wr-rp-assign">
            <AssignmentSidebar
              docked
              open
              onClose={() => setSelectedAssignmentId(null)}
              planId={planId ?? ''}
              assignment={selectedAssignment}
              allAssignments={sortedAssignments}
              employees={candidateEmployees}
              onChanged={() => (planId ? invalidatePlanGantt(qc, planId) : Promise.resolve())}
            />
          </div>
        )}
      </div>

      {gantt && twoLevel && !ganttLoading && (
        <div className="wr-rp-bottom">
          {gantt.employee_load && gantt.employee_load.length > 0 ? (
            <section className="wr-card wr-rp-heat" data-tour="rp-load" aria-label="Загрузка сотрудников по дням">
              <PlanLoadHeatmap
                compact
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
          ) : (
            <section className="wr-card wr-rp-heat" aria-label="Загрузка сотрудников по дням">
              <h2 className="rpc-card-title">Загрузка сотрудников по дням</h2>
              <p className="wr-rp-empty-text">Загрузки пока нет — нажмите «Распределить», чтобы рассчитать план.</p>
            </section>
          )}
          <section className="wr-card wr-rp-norm" aria-label="Нормированные работы">
            {gantt.reserve && gantt.plan.team ? (
              /* key — план: при открытии другого плана сводка заново решает, развернуться ли. */
              <NormedReserveSummary key={gantt.plan.id} reserve={gantt.reserve} compact />
            ) : (
              <>
                <h2 className="rpc-card-title">Нормированные работы — запас квартала</h2>
                <p className="wr-rp-empty-text">Нормированных работ в квартале нет</p>
              </>
            )}
          </section>
        </div>
      )}

      <RpPageModals state={state} />
    </div>
  );
}
