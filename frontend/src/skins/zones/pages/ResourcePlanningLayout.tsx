import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { Alert, Badge, Button, Empty, Input, Modal, Popover, Select, Segmented, Spin } from 'antd';
import { Check, Copy, LockKeyhole, PanelBottomOpen, SlidersHorizontal } from 'lucide-react';
import '../../../utils/gantt.css';
import './resource-planning.css';
import PlanQualityBadge from '../../../components/resource-planning/PlanQualityBadge';
import GanttChart from '../../../components/resource-planning/GanttChart';
import ConflictPanel from '../../../components/resource-planning/ConflictPanel';
import ScheduledBlocksModal from '../../../components/resource-planning/ScheduledBlocksModal';
import AssignmentSidebar from '../../../components/resource-planning/AssignmentSidebar';
import PlanLoadHeatmap from '../../../components/resource-planning/PlanLoadHeatmap';
import NormedReserveSummary from '../../../components/resource-planning/NormedReserveSummary';
import AppearanceModal from '../../../components/resource-planning/AppearanceModal';
import DetailSheet from '../../../components/common/DetailSheet';
import BulkResetDropdown from '../../../components/resource-planning/BulkResetDropdown';
import RpViewOptions from '../../../components/resource-planning/RpViewOptions';
import type { RpLayout } from '../../../components/resource-planning/GanttRows';
import type { TimelineScale } from '../../../utils/gantt';
import { fmtHours, overuseCount, overuseLabel, usedHours, visibleReserveRows } from '../../../utils/normedReserve';
import type { ReserveOut } from '../../../api/resourcePlanning';
import { AppearanceContext } from '../../../contexts/AppearanceContext';
import { zonesAppearance } from '../rpAppearance';
import { planStatusTag, type ResourcePlanningPageState } from '../../../hooks/useResourcePlanningPage';
import ZonesBand, { BandField } from '../ZonesBand';

const SCALE_CAPTION: Record<TimelineScale, string> = { day: 'по дням', week: 'по неделям', month: 'по месяцам' };

const RESERVE_TITLE = 'Нормированные работы — запас квартала';

const PHASES = ['analyst', 'dev', 'qa', 'opo'] as const;
/** Фазы для подписи диаграммы — какие есть в плане; план пуст — все. */
function legendPhases(assignments: { phase: string }[]): (typeof PHASES)[number][] {
  const present = PHASES.filter((ph) => assignments.some((a) => a.phase === ph));
  return present.length ? present : [...PHASES];
}

/** «в 1 виде работ», «в 3 видах работ». */
const kindsLabel = (n: number) => `в ${n} ${n % 10 === 1 && n % 100 !== 11 ? 'виде' : 'видах'} работ`;

/** Итог запаса по всем видам работ квартала. */
function reserveTotals(reserve: ReserveOut) {
  const rows = reserve.roles.flatMap((r) => r.rows);
  const sum = (f: (row: (typeof rows)[number]) => number) => rows.reduce((n, row) => n + f(row), 0);
  return {
    kinds: rows.length,
    planned: sum((r) => r.planned_hours),
    used: sum(usedHours),
    remaining: sum((r) => r.remaining_hours),
  };
}

/**
 * Запас нормированных работ одной строкой: заложено, занято, осталось и
 * перерасход; таблица целиком — в панели по кнопке «Подробнее».
 */
function ReserveLine({ reserve, open, onOpen }: { reserve: ReserveOut | null; open: boolean; onOpen: () => void }) {
  const totals = reserve ? reserveTotals(reserve) : null;
  if (!reserve || !totals || totals.kinds === 0) {
    return (
      <section className="zn-card rpz-reserve-line" aria-label={RESERVE_TITLE}>
        <h2>{RESERVE_TITLE}</h2>
        <span className="rpz-reserve-muted">нормированных работ в квартале нет</span>
      </section>
    );
  }
  const over = overuseCount(reserve);
  return (
    <section className="zn-card rpz-reserve-line" aria-label={RESERVE_TITLE}>
      <h2>{RESERVE_TITLE}</h2>
      <span>заложено <b>{fmtHours(totals.planned)}</b></span>
      <span>занято <b>{fmtHours(totals.used)}</b></span>
      <span>осталось <b>{fmtHours(totals.remaining)}</b></span>
      {over > 0
        ? <span className="rpz-reserve-over">перерасход {kindsLabel(over)}</span>
        : <span className="rpz-reserve-muted">перерасхода нет</span>}
      <Button
        size="small"
        className="rpz-reserve-more"
        icon={<PanelBottomOpen size={14} strokeWidth={1.6} />}
        aria-pressed={open}
        onClick={onOpen}
      >
        Подробнее
      </Button>
    </section>
  );
}

/**
 * Над таблицей запаса — итог квартала, как в строке на странице, и сколько
 * видов работ в таблице: она показывает только те, что уже расходуются.
 */
function ReserveSheetNote({ reserve }: { reserve: ReserveOut }) {
  const totals = reserveTotals(reserve);
  const shown = visibleReserveRows(reserve).reduce((n, r) => n + r.rows.length, 0);
  return (
    <p className="rpz-reserve-note">
      За квартал заложено <b>{fmtHours(totals.planned)}</b>, занято <b>{fmtHours(totals.used)}</b>,
      осталось <b>{fmtHours(totals.remaining)}</b>.
      {shown > 0 && shown < totals.kinds && (
        <> В таблице — виды работ, запас которых уже расходуется (заблокированные периоды или работа
          других команд): {shown} из {totals.kinds}.</>
      )}
    </p>
  );
}

/**
 * «Ресурсное планирование» в скине «Цветовые зоны»: заголовок, план и
 * переключатели — в полосе зоны; в теле — конфликты, диаграмма во всю ширину
 * и полоса загрузки внизу. Назначение фазы и запас нормированных работ —
 * в панели подробностей (одна на странице). Экран — в высоту окна.
 */
export default function ResourcePlanningZonesLayout({ rp }: { rp: ResourcePlanningPageState }) {
  const navigate = useNavigate();
  const {
    planId, viewMode, scale, setScale, depDrawMode, blocksOpen, setBlocksOpen,
    showRelayArrows, groupBySubgroup, collapsedSections, onToggleSection,
    forkModalOpen, setForkModalOpen, forkLabel, setForkLabel, forkMutation, submitFork, cancelFork,
    setSelectedAssignmentId, selectedAssignment,
    peopleFilter, setPeopleFilter, togglePerson, highlightedEmployeeId,
    appearanceOpen, setAppearanceOpen, appearanceSettings,
    prefs, patchPrefs, layout,
    plansLoading, gantt, ganttLoading, team, blocks, employees,
    subgroupOrder, subgroupByEmployee, candidateEmployees, blockMembers,
    compute, createPlan, handleCompute, handlePickScenario,
    sortedAssignments, sectionByItem, shownAssignments, shownBookings, peopleOptions,
    conflictAssignmentIds, handleToggleCollapse,
    onCreateDependency, onDeleteDependency, onAssignmentChanged,
    currentScenarioId, scenarioOptions,
  } = rp;
  const appearance = useMemo(() => zonesAppearance(appearanceSettings), [appearanceSettings]);
  const status = gantt ? planStatusTag(gantt.plan.status) : null;
  const effectiveScale: TimelineScale = prefs.hide_weekends ? 'day' : scale;
  const planCaption = gantt?.plan.quarter && gantt.plan.year
    ? `${gantt.plan.quarter} ${gantt.plan.year} · ${SCALE_CAPTION[effectiveScale]}`
    : SCALE_CAPTION[effectiveScale];
  const computing = compute.isPending || gantt?.plan.status === 'computing';

  // На странице одна панель: фаза или запас нормированных работ.
  const [reserveOpen, setReserveOpen] = useState(false);
  const pickAssignment = (id: string) => {
    // Полоса фазы при нажатии не забирает фокус (её можно тянуть) — иначе он остался бы
    // в поле прежней фазы на панели, и Esc не закрывал бы панель.
    const focused = document.activeElement;
    if (focused instanceof HTMLElement && focused.matches('input, textarea') && focused.closest('.detail-sheet')) focused.blur();
    setReserveOpen(false);
    setSelectedAssignmentId(id);
  };
  const openReserve = () => {
    setSelectedAssignmentId(null);
    setReserveOpen(true);
  };
  const reserve = gantt?.reserve && gantt.plan.team ? gantt.reserve : null;
  // Соседние фазы — в порядке строк диаграммы, только те, что на ней видны.
  const bars = shownAssignments.filter((a) => a.start_date && a.end_date);
  const at = selectedAssignment ? bars.findIndex((a) => a.id === selectedAssignment.id) : -1;
  const prevBar = at > 0 ? bars[at - 1] : null;
  const nextBar = at >= 0 && at < bars.length - 1 ? bars[at + 1] : null;
  // Панель ужала диаграмму — выбранная фаза остаётся на виду.
  const selectedId = selectedAssignment?.id;
  useEffect(() => {
    if (!selectedId) return;
    document
      .querySelector(`.rpz-gantt [data-assignment-id="${selectedId}"]`)
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [selectedId]);

  return (
    <AppearanceContext.Provider value={appearance}>
      <div
        className="zn-fit rpz"
        style={{ '--rp-anim-speed': `${appearanceSettings.animation_speed_seconds}s` } as React.CSSProperties}
      >
        <ZonesBand
          title="Ресурсное планирование"
          tools={(
            <Button className="zn-btn-outline" icon={<LockKeyhole size={15} strokeWidth={1.6} />} onClick={() => setBlocksOpen(true)}>
              Заблокированные периоды
            </Button>
          )}
        >
          <div className="zn-band-row zn-band-row-split">
            <div className="zn-band-group">
              <BandField label="План" className="rpz-plan-field">
                <Select
                  data-tour="rp-scenario-select"
                  variant="borderless"
                  loading={plansLoading || createPlan.isPending}
                  placeholder="Выберите утверждённый сценарий"
                  value={currentScenarioId}
                  onChange={handlePickScenario}
                  options={scenarioOptions}
                  popupMatchSelectWidth={false}
                  style={{ minWidth: 200, maxWidth: 320 }}
                  showSearch
                  optionFilterProp="label"
                  allowClear
                  onClear={() => rp.setPlanId(null)}
                  suffixIcon={currentScenarioId ? (
                    <span className="rpz-plan-suffix"><Check size={14} strokeWidth={2} aria-label="выбран" /></span>
                  ) : undefined}
                />
              </BandField>
              {planId && (
                <Button type="primary" loading={computing} onClick={handleCompute} data-tour="rp-distribute">
                  Распределить
                </Button>
              )}
              {status && (
                <span className={`zn-band-pill${gantt?.plan.status === 'ready' ? ' is-ok' : gantt?.plan.status === 'stale' ? ' is-warn' : ''}`}>
                  {gantt?.plan.status === 'ready' && <Check size={13} strokeWidth={2} aria-hidden />}
                  {status.label}
                </span>
              )}
              {gantt?.plan.label && <span className="zn-band-pill">{gantt.plan.label}</span>}
              {gantt?.plan.is_baseline && <span className="zn-band-pill is-dark">Базовый</span>}
              <PlanQualityBadge planId={planId} />
              {planId && gantt && (
                <Button icon={<Copy size={14} strokeWidth={1.6} />} onClick={() => setForkModalOpen(true)}>
                  Сделать копию плана
                </Button>
              )}
              {planId && gantt && <BulkResetDropdown planId={planId} counts={gantt.reset_counts} />}
              {/* Без базового плана сравнение открывается с выбором базы на месте. */}
              {planId && gantt && (
                <Button
                  onClick={() => navigate(gantt.plan.parent_plan_id
                    ? `/resource-planning/compare?base=${gantt.plan.parent_plan_id}&scen=${planId}`
                    : `/resource-planning/compare?scen=${planId}`)}
                  title={gantt.plan.parent_plan_id ? undefined : 'Базовый план выбирается на странице сравнения'}
                >
                  Сравнить с базовым
                </Button>
              )}
            </div>
            <div className="zn-band-group zn-band-group-end">
              {viewMode === 'two-level' && gantt && (
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
              {viewMode === 'two-level' && gantt && (
                <BandField label="Исполнители" data-tour="rp-people-filter">
                  <Select
                    mode="multiple"
                    variant="borderless"
                    allowClear
                    placeholder="все"
                    value={peopleFilter}
                    onChange={setPeopleFilter}
                    options={peopleOptions}
                    maxTagCount="responsive"
                    showSearch={{ optionFilterProp: 'label' }}
                    popupMatchSelectWidth={false}
                    style={{ width: 150 }}
                  />
                </BandField>
              )}
              {viewMode === 'two-level' && (
                <Segmented
                  data-tour="rp-scale"
                  value={effectiveScale}
                  disabled={prefs.hide_weekends}
                  onChange={v => setScale(v as TimelineScale)}
                  options={[
                    { label: 'День', value: 'day' },
                    { label: 'Неделя', value: 'week' },
                    { label: 'Месяц', value: 'month' },
                  ]}
                />
              )}
              <Popover trigger="click" placement="bottomRight" content={<RpViewOptions rp={rp} />}>
                <Badge dot={prefs.hide_weekends || depDrawMode || groupBySubgroup} offset={[-2, 2]}>
                  <Button icon={<SlidersHorizontal size={14} strokeWidth={1.6} />} data-tour="rp-view">Вид</Button>
                </Badge>
              </Popover>
            </div>
          </div>
        </ZonesBand>

        {gantt?.stale_due_to_other_teams && (
          <Alert
            type="warning"
            showIcon
            title={`Планы других команд изменились после расчёта${
              gantt.stale_teams?.length ? ` (${gantt.stale_teams.join(', ')})` : ''
            } — нажмите «Распределить»`}
            action={(
              <Button size="small" loading={computing} onClick={handleCompute}>
                Распределить
              </Button>
            )}
          />
        )}
        {gantt && (
          <ConflictPanel
            variant="zones"
            conflicts={gantt.conflicts}
            planId={planId}
            onSelectAssignment={pickAssignment}
          />
        )}

        {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
        {!planId && !ganttLoading && (
          <section className="zn-card rpz-empty">
            <Empty description="Выберите план или создайте его из утверждённого сценария" />
          </section>
        )}

        {gantt && !ganttLoading && planId && (
          <div className="rpz-main">
            <section className="zn-card rpz-gantt" aria-label="Диаграмма Ганта">
              <div className="zn-card-head">
                <h2>Диаграмма Ганта</h2>
                <span className="zn-card-sub">{planCaption} · щелчок по фазе — подробности</span>
              </div>
              <div className="rpz-gantt-scroll">
                <GanttChart
                  compact
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
                  onAssignmentClick={pickAssignment}
                  hideWeekends={prefs.hide_weekends}
                  highlightedEmployeeId={highlightedEmployeeId}
                  selectedEmployeeIds={peopleFilter}
                  sectionByItem={sectionByItem}
                  subgroupByEmployee={subgroupOrder.length > 0 ? subgroupByEmployee : undefined}
                  collapsedSections={collapsedSections}
                  onToggleSection={onToggleSection}
                  onEmployeeRowClick={togglePerson}
                  onCreateDependency={onCreateDependency}
                  onDeleteDependency={onDeleteDependency}
                />
                {gantt.assignments.length === 0 && (
                  <div className="rpz-gantt-empty">
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="В плане пока нет фаз — нажмите «Распределить», чтобы разложить задачи сценария по людям"
                    />
                  </div>
                )}
              </div>
              <div className="rpz-legend">
                {/* Фазы — только те, что есть в плане: ОПЭ, выключенная с квартала, в подписи не висит. */}
                {legendPhases(gantt.assignments).map((ph) => (
                  <span key={ph}>
                    <i style={{ background: appearance.phase_colors[ph] }} />
                    {{ analyst: 'Анализ', dev: 'Разработка', qa: 'Тестирование', opo: 'ОПЭ' }[ph]}
                  </span>
                ))}
                <span><i className="rpz-lg-conflict" />конфликт</span>
                <span><i className="rpz-lg-cp" />критический путь</span>
                <span><i className="rpz-lg-pin" />закреплено вручную</span>
                <span><i className="rpz-lg-ooq" />за пределами квартала</span>
                <span><i className="rpz-lg-absence" />отсутствие</span>
                <span><i className="rpz-lg-busy" />занят в другой команде</span>
                <span><i className="rpz-lg-holiday" aria-hidden>●</i>праздник</span>
              </div>
            </section>
          </div>
        )}
        {selectedAssignment && planId && (
          <>
            {/* Выбранная фаза обведена на диаграмме, пока открыта панель. */}
            <style>{`.rpz-gantt [data-assignment-id="${selectedAssignment.id}"]{outline:2px solid #17191C;outline-offset:2px;z-index:4}`}</style>
            <AssignmentSidebar
              sheet
              open
              onClose={() => setSelectedAssignmentId(null)}
              planId={planId}
              assignment={selectedAssignment}
              allAssignments={sortedAssignments}
              employees={candidateEmployees}
              onChanged={onAssignmentChanged}
              nav={at >= 0 && (
                <>
                  <Button disabled={!prevBar} onClick={() => prevBar && pickAssignment(prevBar.id)}>← предыдущая</Button>
                  <Button disabled={!nextBar} onClick={() => nextBar && pickAssignment(nextBar.id)}>следующая →</Button>
                </>
              )}
            />
          </>
        )}

        {gantt && !ganttLoading && planId && viewMode === 'two-level' && (
          <ReserveLine reserve={reserve} open={reserveOpen} onOpen={openReserve} />
        )}
        {gantt && !ganttLoading && planId && viewMode === 'two-level' && gantt.employee_load && gantt.employee_load.length > 0 && (
          <div className="rpz-bottom" data-tour="rp-load">
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
          </div>
        )}
        {reserveOpen && !selectedAssignment && reserve && gantt && (
          <DetailSheet
            open
            onClose={() => setReserveOpen(false)}
            ariaLabel={RESERVE_TITLE}
            className="rpz-reserve-sheet"
            title={RESERVE_TITLE}
            subtitle={`${reserve.scenario_name} · ${overuseLabel(reserve) ?? 'перерасхода нет'}`}
          >
            <ReserveSheetNote reserve={reserve} />
            <NormedReserveSummary key={gantt.plan.id} reserve={reserve} bare />
          </DetailSheet>
        )}

        <ScheduledBlocksModal
          open={blocksOpen}
          onClose={() => setBlocksOpen(false)}
          team={team || undefined}
          members={blockMembers}
        />

        <Modal
          open={forkModalOpen}
          title="Сделать копию плана"
          okText="Создать"
          cancelText="Отмена"
          onOk={submitFork}
          onCancel={cancelFork}
          confirmLoading={forkMutation.isPending}
        >
          <Input
            placeholder="Метка сценария (например: «+1 разработчик»)"
            value={forkLabel}
            onChange={e => setForkLabel(e.target.value)}
            autoFocus
          />
        </Modal>

        <AppearanceModal
          open={appearanceOpen}
          current={appearanceSettings}
          onClose={() => setAppearanceOpen(false)}
        />
      </div>
    </AppearanceContext.Provider>
  );
}
