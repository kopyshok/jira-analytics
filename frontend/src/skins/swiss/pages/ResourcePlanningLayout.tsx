import { useMemo, useState, type ComponentProps, type CSSProperties } from 'react';
import { Alert, Badge, Button, Empty, Popover, Segmented, Select, Spin } from 'antd';
import { Lock } from 'lucide-react';
import dayjs from 'dayjs';
import type { ResourcePlanningPageModel } from '../../../hooks/useResourcePlanningPage';
import { usePlanQuality } from '../../../hooks/useResourcePlanning';
import type { AssignmentOut, ReserveOut } from '../../../api/resourcePlanning';
import { fmtHours, overuseCount, usedHours } from '../../../utils/normedReserve';
import DetailSheet from '../../../components/common/DetailSheet';
import { useDetailSheetWidth } from '../../../components/common/detailSheetWidth';
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
import { BlockHead, Figure, Figures, PassportStrip, StripCell, SwissData, SwissPage } from '../components/Passport';
import { useKeepInView } from '../useKeepInView';
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

const PHASE_ORDER: Record<string, number> = { analyst: 0, dev: 1, qa: 2, opo: 3 };
const ddmm = (iso: string | null) => (iso ? dayjs(iso).format('DD.MM') : '—');

/** Итог запаса нормированных работ квартала: заложено, занято, осталось, видов с перерасходом. */
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

/** «1 инициатива», «3 инициативы», «21 инициатива», «17 инициатив». */
function initiativesWord(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'инициатива';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'инициативы';
  return 'инициатив';
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

/** «Назначение» в панели подробностей: число колонок — по ширине тела панели. */
function SheetAssignment(props: Omit<ComponentProps<typeof AssignmentSidebar>, 'columns' | 'docked'>) {
  const width = useDetailSheetWidth();
  const columns = width >= 1500 ? 4 : width >= 1100 ? 3 : width >= 760 ? 2 : 1;
  return <AssignmentSidebar {...props} docked columns={columns} />;
}

/**
 * «Ресурсное планирование» в обложке «Швейцарская»: паспорт полосой под меню
 * (цифры качества плана, выбор плана, действия), ниже во всю ширину конфликты,
 * диаграмма и снизу — загрузка по дням и итог запаса нормированных работ.
 * Назначение фазы и таблица запаса — в панели подробностей (снизу или справа).
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
  // Рабочая область ужалась под панель — выбранная фаза (или итог запаса) остаётся на виду.
  useKeepInView(
    selectedAssignment?.id ?? (reserveShown ? 'reserve' : null),
    selectedAssignment ? '.sw-rp-gantt-scroll .rp-bar-selected' : '.sw-rp-reserve-sum',
  );

  return (
    <SwissPage strip className="sw-rp">
      <PassportStrip eyebrow="2.0 Паспорт экрана" title="Ресурсное планирование">
        <StripCell>
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
        </StripCell>

        <StripCell className="sw-rp-plan">
          {/* Подпись поля и состояние плана — одной строкой над выбором. */}
          <div className="sw-rp-plan-head">
            <span className="sw-field-label">План</span>
            {gantt && status && (
              <span className="sw-rp-plan-state">
                <span className={`sw-status ${status.tone}`}><span className="sw-dot" />{status.label}</span>
                {gantt.plan.is_baseline && <span className="sw-chip">Базовый</span>}
                {gantt.plan.label && <span className="sw-chip is-plain" title="Метка копии плана">{gantt.plan.label}</span>}
              </span>
            )}
          </div>
          <Select
            data-tour="rp-scenario-select"
            variant="underlined"
            aria-label="План"
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
        </StripCell>

        {planId && (
          <StripCell className="sw-strip-cell--btn">
            <Button
              type="primary"
              className="sw-rp-distribute"
              loading={computing}
              onClick={handleCompute}
              data-tour="rp-distribute"
            >
              Распределить
            </Button>
          </StripCell>
        )}

        <StripCell className="sw-strip-links">
          {planId && gantt && (
            <>
              <button type="button" className="sw-link-row" onClick={() => setForkModalOpen(true)}>
                Сделать копию плана
              </button>
              <BulkResetDropdown planId={planId} counts={gantt.reset_counts} />
              {gantt.plan.parent_plan_id && (
                <button type="button" className="sw-link-row" onClick={openCompare}>Сравнить с базовым</button>
              )}
            </>
          )}
          <button type="button" className="sw-link-row" onClick={() => setBlocksOpen(true)}>
            <Lock size={13} strokeWidth={1.5} aria-hidden="true" />
            Заблокированные периоды
          </button>
        </StripCell>
      </PassportStrip>

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
              meta={gantt ? `${quarterLabel} · ${initiatives} ${initiativesWord(initiatives)}` : undefined}
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
                {/* Штриховка на фазе — дни, когда исполнитель недоступен: отсутствие или заблокированный период */}
                <span><i className="lg-absence" />отсутствие или блокировка</span>
                <span><i className="lg-holiday" />праздник</span>
                <span className="sw-rp-legend-hint">щелчок по фазе — её назначение откроется в панели</span>
              </div>
            )}
          </section>
        </div>

        {viewMode === 'two-level' && gantt && (
          <div className={`sw-rp-bottom${reserve ? '' : ' is-single'}`}>
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
            {/* Нормированные работы: на странице — итог, вся таблица — в панели подробностей */}
            {reserve && totals && (
              <section className={`sw-block sw-rp-reserve-sum${reserveShown ? ' is-open' : ''}`} aria-label="Нормированные работы — запас квартала">
                <BlockHead num="2.6" title="Нормированные работы" meta="запас квартала" />
                <dl className="sw-rp-rs-figs">
                  <div><dt>заложено</dt><dd>{fmtHours(totals.planned)}</dd></div>
                  <div><dt>занято</dt><dd>{fmtHours(totals.used)}</dd></div>
                  <div><dt>осталось</dt><dd>{fmtHours(totals.remaining)}</dd></div>
                </dl>
                <div className="sw-rp-rs-foot">
                  {totals.over > 0
                    ? <span className="sw-rp-rs-over">перерасход в {totals.over} {kindsWord(totals.over)} работ</span>
                    : <span className="sw-rp-rs-ok">перерасхода нет</span>}
                  <button type="button" className="sw-link" aria-expanded={reserveShown} onClick={openReserve}>
                    Подробнее
                  </button>
                </div>
              </section>
            )}
          </div>
        )}
      </SwissData>

      <DetailSheet
        open={!!selectedAssignment}
        onClose={() => setSelectedAssignmentId(null)}
        title={selectedAssignment && (
          <>
            <span className="sw-sheet-num">2.4</span>
            {selectedAssignment.backlog_item_key && `${selectedAssignment.backlog_item_key} · `}
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
        className="sw-rp-assign-sheet"
      >
        {selectedAssignment && (
          <SheetAssignment
            open
            onClose={() => setSelectedAssignmentId(null)}
            planId={planId ?? ''}
            assignment={selectedAssignment}
            allAssignments={sortedAssignments}
            employees={candidateEmployees}
            onChanged={onAssignmentChanged}
          />
        )}
      </DetailSheet>

      <DetailSheet
        open={reserveShown}
        onClose={() => setReserveOpen(false)}
        title={<><span className="sw-sheet-num">2.6</span>Нормированные работы — запас квартала</>}
        subtitle={reserve && totals && [
          reserve.scenario_name,
          `заложено ${fmtHours(totals.planned)}`,
          `занято ${fmtHours(totals.used)}`,
          `осталось ${fmtHours(totals.remaining)}`,
          totals.over > 0 ? `перерасход в ${totals.over} ${kindsWord(totals.over)} работ` : 'перерасхода нет',
        ].join(' · ')}
        ariaLabel="Нормированные работы — запас квартала"
        className="sw-rp-reserve-sheet"
      >
        {reserve && gantt && <NormedReserveSummary key={gantt.plan.id} reserve={reserve} defaultExpanded />}
      </DetailSheet>
    </SwissPage>
  );
}
