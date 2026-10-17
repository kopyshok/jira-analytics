import { Alert, Badge, Button, Popover, Segmented, Select, Spin } from 'antd';
import { CaretRightOutlined, CloseOutlined, EyeOutlined, LockOutlined } from '@ant-design/icons';
import '../../../utils/gantt.css';
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
import { PULT_SIGNAL } from '../palette';
import { PcField, PcLamp, PcRow, PcTitle, PModule, PultScreen } from '../ui';
import PultConflicts from './PultConflicts';

const STATUS: Record<string, { label: string; color: string }> = {
  ready: { label: 'Готово', color: PULT_SIGNAL.green },
  stale: { label: 'Требуется пересчёт', color: PULT_SIGNAL.amber },
  computing: { label: 'Считается…', color: PULT_SIGNAL.blue },
  draft: { label: 'Черновик', color: PULT_SIGNAL.grey },
};

/** Левая колонка диаграммы в обложке — уже, чем в Aurora: модуль делит ширину с «Назначением». */
const LEFT_COL = 380;

/**
 * «Ресурсное планирование» в обложке «Пульт»: панель управления экраном,
 * модули: конфликты · Гант · назначение · загрузка · нормированные работы.
 * Данные и обработчики — общий хук страницы, раскладка только рисует.
 */
export default function PultResourcePlanningLayout({ rp }: { rp: ResourcePlanningPageState }) {
  const {
    planId, setPlanId, viewMode, scale, setScale, depDrawMode, setBlocksOpen,
    showRelayArrows, groupBySubgroup, collapsedSections, toggleSection, setForkModalOpen,
    selectedAssignment, setSelectedAssignmentId,
    peopleFilter, setPeopleFilter, peopleOptions, togglePerson, highlightedEmployeeId,
    appearanceSettings, prefs, patchPrefs, layout,
    plansLoading, gantt, ganttLoading, blocks, employees, candidateEmployees,
    subgroupOrder, subgroupByEmployee, compute, createPlan, handleCompute, handlePickScenario,
    sortedAssignments, sectionByItem, shownAssignments, shownBookings, conflictAssignmentIds,
    handleToggleCollapse, createDependency, deleteDependency,
    refreshGantt, openCompare, currentScenarioId, scenarioOptions,
  } = rp;
  const { data: quality } = usePlanQuality(planId);
  const status = gantt ? STATUS[gantt.plan.status] ?? STATUS.draft : null;
  const computing = compute.isPending || gantt?.plan.status === 'computing';

  const panel = (
    <>
      <PcRow>
        <PcTitle title="Ресурсное планирование" />
        <div className="pc-push pc-group rp-pc-view">
          {viewMode === 'two-level' && gantt && (
            <PcField label="Режим">
              <Segmented
                data-tour="rp-layout-switch"
                value={layout}
                onChange={v => patchPrefs({ view_mode: v as RpLayout })}
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

      <div className="rp-mid">
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
          </div>
        </PModule>

        <PModule
          title="Назначение"
          as="aside"
          className="rp-assign-module"
          ariaLabel="Назначение"
          extra={selectedAssignment && (
            <button type="button" className="pm-close" aria-label="Закрыть" onClick={() => setSelectedAssignmentId(null)}>
              <CloseOutlined style={{ fontSize: 10 }} />
            </button>
          )}
        >
          {selectedAssignment ? (
            <div className="rp-assign-scroll">
              <AssignmentSidebar
                docked
                open
                onClose={() => setSelectedAssignmentId(null)}
                planId={planId ?? ''}
                assignment={selectedAssignment}
                allAssignments={sortedAssignments}
                employees={candidateEmployees}
                onChanged={refreshGantt}
              />
            </div>
          ) : (
            <div className="pm-empty">
              Щёлкните фазу на диаграмме — здесь откроются её часы, исполнитель и даты
            </div>
          )}
        </PModule>
      </div>

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
          <PModule title="Нормированные работы — запас квартала" className="rp-reserve-module" ariaLabel="Нормированные работы">
            {gantt?.reserve && gantt.plan.team ? (
              <div className="pm-screen rp-reserve-screen">
                <NormedReserveSummary key={gantt.plan.id} reserve={gantt.reserve} docked />
              </div>
            ) : (
              <div className="pm-empty">
                {gantt ? 'Нормированных работ в квартале нет' : 'Запас квартала появится после выбора плана'}
              </div>
            )}
          </PModule>
        </div>
      )}

      <ResourcePlanningDialogs rp={rp} />
    </PultScreen>
  );
}
