import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Alert, Badge, Button, Empty, Popover, Segmented, Select, Spin } from 'antd';
import { CalculatorOutlined, CheckOutlined, ControlOutlined, LockOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
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
import DetailSheet from '../../../components/common/DetailSheet';
import type { AssignmentOut, ReserveOut } from '../../../api/resourcePlanning';
import { PHASE_LABELS } from '../../../utils/gantt';
import { fmtHours, overuseCount, usedHours } from '../../../utils/normedReserve';
import ConflictStrip from '../components/ConflictStrip';
import { useWidth } from '../useWidth';

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
      <span className="wr-legend-hint">щелчок по фазе — назначение откроется в панели</span>
    </div>
  );
}

const PHASE_ORDER: Record<string, number> = { analyst: 0, dev: 1, qa: 2, opo: 3 };
const ddmm = (iso: string | null) => (iso ? dayjs(iso).format('DD.MM') : '—');

/** Подпись фазы в шапке панели: фаза, исполнитель, часы, сроки. */
function phaseLine(a: AssignmentOut): string {
  return [
    `${PHASE_LABELS[a.phase] ?? a.phase}${a.part_number > 1 ? ` · часть ${a.part_number}` : ''}`,
    a.employee_name ?? (a.phase === 'qa' ? 'QA — без сотрудника' : 'исполнитель не назначен'),
    `${Math.round(a.hours_allocated ?? 0)} ч`,
    `${ddmm(a.start_date)} – ${ddmm(a.end_date)}`,
  ].join(' · ');
}

/** Итог запаса нормированных работ для строки на странице. */
function reserveTotals(reserve: ReserveOut) {
  let planned = 0;
  let used = 0;
  let remaining = 0;
  for (const role of reserve.roles) {
    for (const row of role.rows) {
      planned += row.planned_hours;
      used += usedHours(row);
      remaining += row.remaining_hours;
    }
  }
  return { planned, used, remaining, over: overuseCount(reserve) };
}

/** «в 1 виде», «в 3 видах» работ. */
const kindsWord = (n: number) => (n % 10 === 1 && n % 100 !== 11 ? 'виде' : 'видах');

/**
 * «Ресурсное планирование» в скине «Тёплая» (макет C-resource): панель плана,
 * конфликты, диаграмма Ганта во всю ширину, внизу — загрузка по дням и итог
 * запаса нормированных работ (оба блока есть всегда, без данных — со спокойной
 * подписью). Назначение фазы и вся таблица запаса — в панели подробностей
 * снизу или справа (одна за раз). Страница помещается в экран, длинные части
 * прокручиваются внутри своих блоков. Данные и обработчики — общие с
 * раскладкой Aurora (useResourcePlanningPage).
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
  const refreshGantt = () => (planId ? invalidatePlanGantt(qc, planId) : Promise.resolve());

  // На странице одна панель подробностей: назначение фазы или запас нормированных работ.
  const [reserveOpen, setReserveOpen] = useState(false);
  if (reserveOpen && selectedAssignment) setReserveOpen(false);
  const reserve = gantt?.reserve && gantt.plan.team ? gantt.reserve : null;
  const totals = useMemo(() => (reserve ? reserveTotals(reserve) : null), [reserve]);
  const reserveShown = reserveOpen && !!reserve && twoLevel;
  const openReserve = () => {
    setSelectedAssignmentId(null);
    setReserveOpen(true);
  };

  // Соседние фазы для стрелок в шапке панели: задачи — в порядке диаграммы, внутри — фазы по порядку.
  const phaseNav = useMemo(() => {
    const itemIdx = new Map<string, number>();
    for (const a of shownAssignments) if (!itemIdx.has(a.backlog_item_id)) itemIdx.set(a.backlog_item_id, itemIdx.size);
    return shownAssignments
      .filter((a) => a.start_date && a.end_date)
      .sort((a, b) =>
        (itemIdx.get(a.backlog_item_id) ?? 0) - (itemIdx.get(b.backlog_item_id) ?? 0)
        || (PHASE_ORDER[a.phase] ?? 9) - (PHASE_ORDER[b.phase] ?? 9)
        || (a.start_date ?? '').localeCompare(b.start_date ?? '')
        || a.part_number - b.part_number);
  }, [shownAssignments]);
  const navIdx = selectedAssignment ? phaseNav.findIndex((a) => a.id === selectedAssignment.id) : -1;
  const prevPhase = navIdx > 0 ? phaseNav[navIdx - 1] : null;
  const nextPhase = navIdx >= 0 && navIdx < phaseNav.length - 1 ? phaseNav[navIdx + 1] : null;

  // Рабочая область ужалась под панель — выбранная фаза остаётся на виду (и при переходе стрелками).
  const selectedId = selectedAssignment?.id;
  useEffect(() => {
    if (!selectedId) return;
    const frame = requestAnimationFrame(() =>
      document.querySelector('.wr-rp-gantt .rpc-bar.is-selected')?.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
    return () => cancelAnimationFrame(frame);
  }, [selectedId]);
  const [assignRef, assignWidth] = useWidth<HTMLDivElement>();
  const assignCols = assignWidth >= 1440 ? 4 : assignWidth >= 1000 ? 3 : assignWidth >= 700 ? 2 : 1;

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
          {/* Нормированные работы: на странице — итог, вся таблица — в панели подробностей. */}
          <section className="wr-card wr-rp-norm" aria-label="Нормированные работы — запас квартала">
            <h2 className="rpc-card-title">Нормированные работы — запас квартала</h2>
            {reserve && totals ? (
              <>
                <p className="wr-rp-norm-scn" title={reserve.scenario_name}>{reserve.scenario_name}</p>
                <dl className="wr-rp-norm-figs">
                  <div><dt>Заложено</dt><dd>{fmtHours(totals.planned)}</dd></div>
                  <div><dt>Занято</dt><dd>{fmtHours(totals.used)}</dd></div>
                  <div><dt>Осталось</dt><dd>{fmtHours(totals.remaining)}</dd></div>
                </dl>
                <div className="wr-rp-norm-foot">
                  {totals.over > 0
                    ? <span className="wr-pill is-sm is-bad">перерасход в {totals.over} {kindsWord(totals.over)} работ</span>
                    : <span className="wr-rp-empty-text">перерасхода нет</span>}
                  <Button size="small" aria-expanded={reserveShown} onClick={openReserve}>Подробнее</Button>
                </div>
              </>
            ) : (
              <p className="wr-rp-empty-text">Нормированных работ в квартале нет</p>
            )}
          </section>
        </div>
      )}

      <DetailSheet
        open={!!selectedAssignment}
        onClose={() => setSelectedAssignmentId(null)}
        title={selectedAssignment && (
          <>
            {selectedAssignment.backlog_item_key && <span className="wr-sheet-key">{selectedAssignment.backlog_item_key}</span>}
            {selectedAssignment.backlog_item_title}
          </>
        )}
        subtitle={selectedAssignment && phaseLine(selectedAssignment)}
        extra={(prevPhase || nextPhase) && (
          <>
            <Button size="small" disabled={!prevPhase} onClick={() => prevPhase && setSelectedAssignmentId(prevPhase.id)}>
              ← предыдущая
            </Button>
            <Button size="small" disabled={!nextPhase} onClick={() => nextPhase && setSelectedAssignmentId(nextPhase.id)}>
              следующая →
            </Button>
          </>
        )}
        ariaLabel="Назначение"
        className="wr-rp-assign-sheet"
      >
        {selectedAssignment && (
          <div ref={assignRef}>
            <AssignmentSidebar
              docked
              columns={assignCols}
              open
              onClose={() => setSelectedAssignmentId(null)}
              planId={planId ?? ''}
              assignment={selectedAssignment}
              allAssignments={sortedAssignments}
              employees={candidateEmployees}
              onChanged={refreshGantt}
            />
          </div>
        )}
      </DetailSheet>

      <DetailSheet
        open={reserveShown}
        onClose={() => setReserveOpen(false)}
        title="Нормированные работы — запас квартала"
        subtitle={reserve && totals
          && `${reserve.scenario_name} · заложено ${fmtHours(totals.planned)} · занято ${fmtHours(totals.used)} · осталось ${fmtHours(totals.remaining)}`}
        ariaLabel="Нормированные работы — запас квартала"
        className="wr-rp-reserve-sheet"
      >
        {/* key — план: при открытии другого плана сводка заново решает, развернуться ли. */}
        {reserve && gantt && <NormedReserveSummary key={gantt.plan.id} reserve={reserve} compact />}
      </DetailSheet>

      <RpPageModals state={state} />
    </div>
  );
}
