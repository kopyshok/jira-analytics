import { useLayoutEffect, useRef } from 'react';
import '../utils/gantt.css';
import { Alert, Badge, Button, Empty, Popover, Select, Segmented, Space, Spin, Tag, Tooltip } from 'antd';
// Скрытые режимы Портфель/Ресурсы/Plane остаются в коде (PlaneGantt, GanttRows viewMode union)
// PM хочет вернуться к ним после доработки; см. project_resource_planning_modes_hidden.md.
import {
  CalculatorOutlined,
  ControlOutlined,
  CopyOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import PlanQualityBadge from '../components/resource-planning/PlanQualityBadge';
import GanttChart from '../components/resource-planning/GanttChart';
import PlaneGantt from '../components/resource-planning/PlaneGantt';
import ConflictPanel from '../components/resource-planning/ConflictPanel';
import AssignmentSidebar from '../components/resource-planning/AssignmentSidebar';
import PlanLoadHeatmap from '../components/resource-planning/PlanLoadHeatmap';
import NormedReserveSummary from '../components/resource-planning/NormedReserveSummary';
import BulkResetDropdown from '../components/resource-planning/BulkResetDropdown';
import type { RpLayout } from '../components/resource-planning/GanttRows';
import type { TimelineScale } from '../utils/gantt';
import { AppearanceProvider } from '../contexts/AppearanceContext';
import { useSkin } from '../contexts/ThemeContext';
import { DARK_THEME } from '../utils/constants';
import { useResourcePlanningPage, type ResourcePlanningPageState } from '../hooks/useResourcePlanningPage';
import PultResourcePlanningLayout from '../skins/pult/pages/ResourcePlanningLayout';
import ResourcePlanningDialogs from '../components/resource-planning/ResourcePlanningDialogs';
import RpViewOptions from '../components/resource-planning/RpViewOptions';

function AuroraResourcePlanningLayout({ rp }: { rp: ResourcePlanningPageState }) {
  const {
    planId, setPlanId, viewMode, scale, setScale, depDrawMode, setBlocksOpen,
    showRelayArrows, groupBySubgroup,
    collapsedSections, toggleSection, setForkModalOpen,
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
  const stickyRef = useRef<HTMLDivElement | null>(null);
  const pageRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const el = stickyRef.current;
    const page = pageRef.current;
    if (!el || !page) return;
    const apply = () => {
      page.style.setProperty('--rp-page-sticky-h', `${el.offsetHeight}px`);
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={pageRef} style={{ padding: '16px 24px', '--rp-anim-speed': `${appearanceSettings.animation_speed_seconds}s` } as React.CSSProperties}>
      <div
        ref={stickyRef}
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 50,
          background: DARK_THEME.pageBg,
          marginLeft: -24,
          marginRight: -24,
          paddingLeft: 24,
          paddingRight: 24,
          paddingTop: 16,
          marginTop: -16,
          paddingBottom: 8,
          marginBottom: 8,
          boxShadow: '0 2px 8px rgba(0,0,0,0.35)',
        }}
      >
        <PageHeader
          title="Ресурсное планирование"
          actions={
            <Button icon={<SettingOutlined />} onClick={() => setBlocksOpen(true)} size="small">
              Заблокированные периоды
            </Button>
          }
        />

        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <Select
          data-tour="rp-scenario-select"
          loading={plansLoading || createPlan.isPending}
          placeholder="Выберите утверждённый сценарий"
          value={currentScenarioId}
          onChange={handlePickScenario}
          options={scenarioOptions}
          style={{ minWidth: 260, maxWidth: 360, flex: '1 1 260px' }}
          showSearch
          optionFilterProp="label"
          allowClear
          onClear={() => setPlanId(null)}
        />
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
        {gantt && (() => {
          const s = gantt.plan.status;
          const label = s === 'ready' ? 'Готово'
            : s === 'stale' ? 'Требуется пересчёт'
            : s === 'computing' ? 'Считается…'
            : 'Черновик';
          const color = s === 'ready' ? 'cyan'
            : s === 'stale' ? 'orange'
            : s === 'computing' ? 'blue'
            : 'default';
          return <Tag color={color}>{label}</Tag>;
        })()}
        {gantt?.plan.label && <Tag color="purple">{gantt.plan.label}</Tag>}
        {gantt?.plan.is_baseline && <Tag color="cyan">Базовый</Tag>}
        <PlanQualityBadge planId={planId} />
        {planId && gantt && (
          <Tooltip title="Сделать копию плана">
            <Button size="small" icon={<CopyOutlined />} aria-label="Сделать копию плана" onClick={() => setForkModalOpen(true)} />
          </Tooltip>
        )}
        {planId && gantt && (
          <BulkResetDropdown planId={planId} counts={gantt.reset_counts} />
        )}
        {gantt?.plan.parent_plan_id && (
          <Button
            size="small"
            onClick={openCompare}
          >
            Сравнить с базовым
          </Button>
        )}

        {/* Вид диаграммы: частые переключатели на виду, редкие — в окне «Вид». */}
        <Space size={6} style={{ marginLeft: 'auto' }}>
          {viewMode === 'two-level' && gantt && (
            <Segmented
              key={layoutSwitchKey}
              data-tour="rp-layout-switch"
              size="small"
              value={layout}
              onChange={v => changeLayout(v as RpLayout)}
              options={[
                { label: 'Задачи', value: 'tasks' },
                { label: 'Исполнители', value: 'people' },
              ]}
            />
          )}
          {viewMode === 'two-level' && gantt && (
            <Select
              data-tour="rp-people-filter"
              mode="multiple"
              size="small"
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
          )}
          {viewMode === 'two-level' && (
            <Segmented
              data-tour="rp-scale"
              size="small"
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
          <Popover
            trigger="click"
            placement="bottomRight"
            content={<RpViewOptions rp={rp} />}
          >
            <Badge dot={prefs.hide_weekends || depDrawMode || groupBySubgroup} offset={[-2, 2]}>
              <Button size="small" icon={<ControlOutlined />} data-tour="rp-view">
                Вид
              </Button>
            </Badge>
          </Popover>
        </Space>
        </div>
      </div>

      {createFailure && createFailure.plan.scenario_id !== currentScenarioId && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 8 }}
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
          style={{ marginBottom: 8 }}
          title={`Планы других команд изменились после расчёта${
            gantt.stale_teams?.length ? ` (${gantt.stale_teams.join(', ')})` : ''
          } — нажмите «Распределить»`}
          action={
            <Button
              size="small"
              loading={compute.isPending || gantt.plan.status === 'computing'}
              onClick={handleCompute}
            >
              Распределить
            </Button>
          }
        />
      )}
      {gantt && viewMode !== 'plane' && (
        <ConflictPanel
          conflicts={gantt.conflicts}
          planId={planId}
          onSelectAssignment={(id) => setSelectedAssignmentId(id)}
        />
      )}

      {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
      {!planId && !ganttLoading && (
        <Empty description="Выберите план или создайте его из утверждённого сценария" />
      )}
      {gantt && !ganttLoading && planId && viewMode === 'plane' && (
        <PlaneGantt
          assignments={sortedAssignments}
          blocks={blocks}
          employees={employees}
          employeeLoad={gantt.employee_load}
          quarter={gantt.plan.quarter ?? 'Q1'}
          year={gantt.plan.year ?? new Date().getFullYear()}
          planLabel={gantt.plan.label ?? null}
          onAssignmentClick={(id) => setSelectedAssignmentId(id)}
        />
      )}
      {gantt && !ganttLoading && planId && viewMode !== 'plane' && (
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
        />
      )}

      {gantt?.reserve && gantt.plan.team && viewMode === 'two-level' && (
        // key — план: при открытии другого плана сводка заново решает, развернуться ли.
        <NormedReserveSummary key={gantt.plan.id} reserve={gantt.reserve} />
      )}

      {gantt?.employee_load && gantt.employee_load.length > 0 && viewMode === 'two-level' && (
        <div data-tour="rp-load">
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
        </div>
      )}

      <AssignmentSidebar
        open={!!selectedAssignment}
        onClose={() => setSelectedAssignmentId(null)}
        planId={planId ?? ''}
        assignment={selectedAssignment}
        allAssignments={sortedAssignments}
        employees={candidateEmployees}
        onChanged={refreshGantt}
      />

      <ResourcePlanningDialogs rp={rp} />
    </div>
  );
}

function ResourcePlanningPageInner() {
  const rp = useResourcePlanningPage();
  const skin = useSkin();
  if (skin === 'pult') return <PultResourcePlanningLayout rp={rp} />;
  return <AuroraResourcePlanningLayout rp={rp} />;
}

export default function ResourcePlanningPage() {
  return (
    <AppearanceProvider>
      <ResourcePlanningPageInner />
    </AppearanceProvider>
  );
}
