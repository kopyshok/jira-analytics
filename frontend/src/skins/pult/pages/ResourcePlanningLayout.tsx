import { useEffect, useMemo, useState } from 'react';
import { Alert, Badge, Button, Popover, Segmented, Select, Spin } from 'antd';
import { CaretRightOutlined, EyeOutlined, LockOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import '../../../utils/gantt.css';
import DetailSheet from '../../../components/common/DetailSheet';
import GanttChart from '../../../components/resource-planning/GanttChart';
import AssignmentSidebar from '../../../components/resource-planning/AssignmentSidebar';
import PlanLoadHeatmap from '../../../components/resource-planning/PlanLoadHeatmap';
import NormedReserveSummary from '../../../components/resource-planning/NormedReserveSummary';
import BulkResetDropdown from '../../../components/resource-planning/BulkResetDropdown';
import ResourcePlanningDialogs from '../../../components/resource-planning/ResourcePlanningDialogs';
import RpViewOptions from '../../../components/resource-planning/RpViewOptions';
import type { RpLayout } from '../../../components/resource-planning/GanttRows';
import type { TimelineScale } from '../../../utils/gantt';
import { PHASE_LABELS } from '../../../utils/gantt';
import { usePlanQuality } from '../../../hooks/useResourcePlanning';
import type { ResourcePlanningPageState } from '../../../hooks/useResourcePlanningPage';
import type { AssignmentOut, ReserveOut } from '../../../api/resourcePlanning';
import { fmtHours, overuseCount, usedHours } from '../../../utils/normedReserve';
import { PULT_SIGNAL } from '../palette';
import { PcField, PcLamp, PcRow, PcTitle, PModule, PultScreen } from '../ui';
import { useWidth } from '../useWidth';
import PultConflicts from './PultConflicts';

const STATUS: Record<string, { label: string; color: string }> = {
  ready: { label: 'Готово', color: PULT_SIGNAL.green },
  stale: { label: 'Требуется пересчёт', color: PULT_SIGNAL.amber },
  computing: { label: 'Считается…', color: PULT_SIGNAL.blue },
  draft: { label: 'Черновик', color: PULT_SIGNAL.grey },
};

/** Левая колонка диаграммы в обложке — уже, чем в Aurora. */
const LEFT_COL = 380;

const PHASE_ORDER: Record<string, number> = { analyst: 0, dev: 1, qa: 2, opo: 3 };
const ddmm = (iso: string | null) => (iso ? dayjs(iso).format('DD.MM') : '—');

/** Итог запаса нормированных работ для страницы: заложено, занято, осталось, перерасход. */
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

/** Подпись фазы в шапке панели: фаза, исполнитель, часы, сроки. */
function phaseLine(a: AssignmentOut): string {
  return [
    `${PHASE_LABELS[a.phase] ?? a.phase}${a.part_number > 1 ? ` · часть ${a.part_number}` : ''}`,
    a.employee_name ?? (a.phase === 'qa' ? 'QA — без сотрудника' : 'исполнитель не назначен'),
    `${Math.round(a.hours_allocated ?? 0)} ч`,
    `${ddmm(a.start_date)}–${ddmm(a.end_date)}`,
  ].join(' · ');
}

/**
 * «Ресурсное планирование» в обложке «Пульт»: панель управления экраном,
 * модули: конфликты · Гант · загрузка · итог нормированных работ; назначение фазы
 * и таблица запаса — в панели подробностей (снизу или справа).
 * Данные и обработчики — общий хук страницы, раскладка только рисует.
 */
export default function PultResourcePlanningLayout({ rp }: { rp: ResourcePlanningPageState }) {
  const {
    planId, setPlanId, viewMode, scale, setScale, depDrawMode, setBlocksOpen,
    showRelayArrows, groupBySubgroup, collapsedSections, toggleSection, setForkModalOpen,
    selectedAssignment, setSelectedAssignmentId,
    peopleFilter, setPeopleFilter, peopleOptions, togglePerson, highlightedEmployeeId,
    appearanceSettings, prefs, layout, layoutSwitchKey, changeLayout,
    plansLoading, gantt, ganttLoading, blocks, employees, candidateEmployees,
    subgroupOrder, subgroupByEmployee, compute, createPlan, createFailure, createPlanFor,
    handleCompute, handlePickScenario, approvedScenarios,
    sortedAssignments, sectionByItem, shownAssignments, shownBookings, conflictAssignmentIds,
    handleToggleCollapse, createDependency, deleteDependency,
    refreshGantt, openCompare, currentScenarioId, scenarioOptions,
  } = rp;
  const { data: quality } = usePlanQuality(planId);
  const status = gantt ? STATUS[gantt.plan.status] ?? STATUS.draft : null;
  const computing = compute.isPending || gantt?.plan.status === 'computing';

  // На странице одна панель подробностей: фаза плана или запас нормированных работ.
  const [reserveOpen, setReserveOpen] = useState(false);
  if (reserveOpen && selectedAssignment) setReserveOpen(false);
  const reserve = gantt?.reserve && gantt.plan.team ? gantt.reserve : null;
  const totals = useMemo(() => (reserve ? reserveTotals(reserve) : null), [reserve]);
  const reserveShown = reserveOpen && !!reserve && viewMode === 'two-level';
  const openReserve = () => {
    setSelectedAssignmentId(null);
    setReserveOpen(true);
  };

  // Соседние фазы для стрелок в шапке панели: порядок задач диаграммы, внутри — фазы по порядку.
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
      document.querySelector('.rp-gantt-screen .rp-bar-selected')?.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
    return () => cancelAnimationFrame(frame);
  }, [selectedId]);
  const [assignRef, assignWidth] = useWidth<HTMLDivElement>();
  const assignCols = assignWidth >= 1500 ? 4 : assignWidth >= 1100 ? 3 : assignWidth >= 800 ? 2 : 1;

  const panel = (
    <>
      <PcRow>
        <PcTitle title="Ресурсное планирование" />
        <div className="pc-push pc-group rp-pc-view">
          {viewMode === 'two-level' && gantt && (
            <PcField label="Режим">
              <Segmented
                key={layoutSwitchKey}
                data-tour="rp-layout-switch"
                value={layout}
                onChange={v => changeLayout(v as RpLayout)}
                options={[
                  { label: 'Задачи', value: 'tasks' },
                  { label: 'Исполнители', value: 'people' },
                ]}
              />
            </PcField>
          )}
          {viewMode === 'two-level' && gantt && (
            <PcField label="Исполнители">
              <Select
                data-tour="rp-people-filter"
                mode="multiple"
                allowClear
                prefix="Исполнители:"
                placeholder="все"
                value={peopleFilter}
                onChange={setPeopleFilter}
                options={peopleOptions}
                maxTagCount="responsive"
                showSearch={{ optionFilterProp: 'label' }}
                style={{ width: 220 }}
              />
            </PcField>
          )}
          {viewMode === 'two-level' && (
            <PcField label="Масштаб">
              <Segmented
                data-tour="rp-scale"
                className="pc-accent-seg"
                value={prefs.hide_weekends ? 'day' : scale}
                disabled={prefs.hide_weekends}
                onChange={v => setScale(v as TimelineScale)}
                options={[
                  { label: 'День', value: 'day' },
                  { label: 'Неделя', value: 'week' },
                  { label: 'Месяц', value: 'month' },
                ]}
              />
            </PcField>
          )}
          <Popover trigger="click" placement="bottomRight" content={<RpViewOptions rp={rp} />}>
            <Badge dot={prefs.hide_weekends || depDrawMode || groupBySubgroup} offset={[-2, 2]}>
              <Button className="is-key" icon={<EyeOutlined />} data-tour="rp-view">Вид</Button>
            </Badge>
          </Popover>
          <Button icon={<LockOutlined />} onClick={() => setBlocksOpen(true)} style={{ marginLeft: 10 }}>
            Заблокированные периоды
          </Button>
        </div>
      </PcRow>
      <PcRow>
        <PcField label="План">
          <Select
            data-tour="rp-scenario-select"
            loading={plansLoading || createPlan.isPending}
            placeholder="Выберите утверждённый сценарий"
            value={currentScenarioId}
            onChange={handlePickScenario}
            options={scenarioOptions}
            style={{ width: 320 }}
            showSearch
            optionFilterProp="label"
            allowClear
            onClear={() => setPlanId(null)}
          />
        </PcField>
        {planId && (
          <Button
            icon={<CaretRightOutlined />}
            type="primary"
            loading={computing}
            onClick={handleCompute}
            data-tour="rp-distribute"
          >
            Распределить
          </Button>
        )}
        {status && (
          <PcField label="Статус">
            <PcLamp color={status.color}><b>{status.label.toUpperCase()}</b></PcLamp>
          </PcField>
        )}
        {gantt && (gantt.plan.is_baseline || gantt.plan.label) && (
          <PcField label="План">
            <span className="pc-group">
              {gantt.plan.is_baseline && <PcLamp dark>БАЗОВЫЙ</PcLamp>}
              {gantt.plan.label && <PcLamp>{gantt.plan.label}</PcLamp>}
            </span>
          </PcField>
        )}
        {quality && (
          <PcField label="Качество плана">
            <span className="pc-group" title="Качество расписания: % перегруженных дней · число просрочек · среднее использование ёмкости">
              <PcLamp color={quality.overload_days_pct > 20 ? PULT_SIGNAL.red : quality.overload_days_pct > 5 ? PULT_SIGNAL.amber : PULT_SIGNAL.green}>
                Перегрузки: <b>{quality.overload_days_pct}%</b>
              </PcLamp>
              <PcLamp color={quality.late_count > 0 ? PULT_SIGNAL.red : PULT_SIGNAL.green}>
                Просрочки: <b>{quality.late_count}</b>
              </PcLamp>
              <PcLamp color={PULT_SIGNAL.green}>
                Утилизация: <b>{quality.mean_utilization_pct}%</b>
              </PcLamp>
            </span>
          </PcField>
        )}
        {planId && gantt && (
          <div className="pc-group" style={{ marginLeft: 8 }}>
            <Button onClick={() => setForkModalOpen(true)}>Сделать копию плана</Button>
            <BulkResetDropdown planId={planId} counts={gantt.reset_counts} />
            {gantt.plan.parent_plan_id && <Button onClick={openCompare}>Сравнить с базовым</Button>}
          </div>
        )}
      </PcRow>
    </>
  );

  const ganttBody = (() => {
    if (ganttLoading) return <div className="pm-empty"><Spin /></div>;
    if (!planId || !gantt) {
      return <div className="pm-empty">Выберите план или создайте его из утверждённого сценария</div>;
    }
    return (
      <div className="pm-screen rp-gantt-screen">
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
          selectedAssignmentId={selectedAssignment?.id ?? null}
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
        />
      </div>
    );
  })();

  const phaseColors = appearanceSettings.phase_colors as Record<string, string>;

  return (
    <PultScreen panel={panel} bodyClassName="rp-pult">
      {createFailure && createFailure.plan.scenario_id !== currentScenarioId && (
        <Alert
          type="error"
          showIcon
          title={`Не удалось создать план по сценарию «${
            approvedScenarios.find(s => s.id === createFailure.plan.scenario_id)?.name ?? '—'
          }»`}
          description={createFailure.reason || undefined}
          action={
            <Button size="small" loading={createPlan.isPending} onClick={() => createPlanFor(createFailure.plan)}>
              Повторить
            </Button>
          }
        />
      )}
      {gantt?.stale_due_to_other_teams && (
        <Alert
          type="warning"
          showIcon
          title={`Планы других команд изменились после расчёта${
            gantt.stale_teams?.length ? ` (${gantt.stale_teams.join(', ')})` : ''
          } — нажмите «Распределить»`}
          action={<Button size="small" loading={computing} onClick={handleCompute}>Распределить</Button>}
        />
      )}

      {gantt && viewMode !== 'plane' && (
        <PultConflicts
          conflicts={gantt.conflicts}
          planId={planId}
          onSelectAssignment={(id) => setSelectedAssignmentId(id)}
        />
      )}
      {!gantt && viewMode !== 'plane' && (
        <PModule
          title="Конфликты"
          className="rp-conflicts"
          ariaLabel="Конфликты"
          extra={<span className="rp-conf-none">{ganttLoading ? 'загрузка…' : 'план не выбран'}</span>}
        />
      )}

      <PModule title="Диаграмма Ганта" className="rp-gantt-module" ariaLabel="Диаграмма Ганта">
        {ganttBody}
        <div className="pm-legend">
          {(['analyst', 'dev', 'qa', 'opo'] as const).map((p) => (
            <span key={p}><i style={{ background: phaseColors[p] }} />{PHASE_LABELS[p]}</span>
          ))}
          <span><i className="lg-conflict" />конфликт</span>
          <span><i className="lg-cp" />критический путь</span>
          <span><i className="lg-pinned" />закреплено вручную</span>
          <span><i className="lg-ooq" />за пределами квартала</span>
          <span><i className="lg-absence" />отпуск</span>
          {gantt && <span className="rp-legend-hint">щелчок по фазе — её назначение откроется в панели</span>}
        </div>
      </PModule>

      {viewMode === 'two-level' && (
        <div className="rp-bottom">
          {gantt && gantt.employee_load && gantt.employee_load.length > 0 ? (
            <section className="pm rp-heat-module" aria-label="Загрузка сотрудников по дням" data-tour="rp-load">
              <PlanLoadHeatmap
                docked
                title={<span className="pm-cap">Загрузка сотрудников по дням</span>}
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
            <PModule title="Загрузка сотрудников по дням" className="rp-heat-module" ariaLabel="Загрузка сотрудников по дням">
              <div className="pm-empty">
                {gantt ? 'В плане нет назначений — загрузки по дням нет' : 'Загрузка по дням появится после выбора плана'}
              </div>
            </PModule>
          )}
          {/* Нормированные работы: на странице — итог, вся таблица — в панели подробностей */}
          <PModule title="Нормированные работы — запас квартала" className="rp-reserve-sum" ariaLabel="Нормированные работы — запас квартала">
            {totals ? (
              <>
                <dl className="pm-screen rp-rs-figs">
                  <div><dt>заложено</dt><dd className="num">{fmtHours(totals.planned)}</dd></div>
                  <div><dt>занято</dt><dd className="num">{fmtHours(totals.used)}</dd></div>
                  <div><dt>осталось</dt><dd className="num">{fmtHours(totals.remaining)}</dd></div>
                </dl>
                <div className="rp-rs-foot">
                  {totals.over > 0
                    ? <span className="rp-rs-over">перерасход в {totals.over} {kindsWord(totals.over)} работ</span>
                    : <span className="rp-rs-ok">перерасхода нет</span>}
                  <Button size="small" className="rp-rs-more" aria-expanded={reserveShown} onClick={openReserve}>
                    Подробнее
                  </Button>
                </div>
              </>
            ) : (
              <div className="pm-empty">
                {gantt ? 'Нормированных работ в квартале нет' : 'Запас квартала появится после выбора плана'}
              </div>
            )}
          </PModule>
        </div>
      )}

      <DetailSheet
        open={!!selectedAssignment}
        onClose={() => setSelectedAssignmentId(null)}
        title={selectedAssignment && (
          <>
            {selectedAssignment.backlog_item_key && <span className="num">{selectedAssignment.backlog_item_key} · </span>}
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
        className="rp-assign-sheet"
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
        className="rp-reserve-sheet"
      >
        {reserve && gantt && (
          <section className="pm rp-reserve-module">
            <div className="pm-screen rp-reserve-screen">
              <NormedReserveSummary key={gantt.plan.id} reserve={reserve} docked />
            </div>
          </section>
        )}
      </DetailSheet>

      <ResourcePlanningDialogs rp={rp} />
    </PultScreen>
  );
}
