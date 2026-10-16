import { useLayoutEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import '../utils/gantt.css';
import { Alert, Badge, Button, Empty, Input, Modal, Popover, Select, Segmented, Space, Spin, Tag, Tooltip } from 'antd';
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
import ScheduledBlocksModal from '../components/resource-planning/ScheduledBlocksModal';
import AssignmentSidebar from '../components/resource-planning/AssignmentSidebar';
import PlanLoadHeatmap from '../components/resource-planning/PlanLoadHeatmap';
import NormedReserveSummary from '../components/resource-planning/NormedReserveSummary';
import AppearanceModal from '../components/resource-planning/AppearanceModal';
import BulkResetDropdown from '../components/resource-planning/BulkResetDropdown';
import RpViewOptions from '../components/resource-planning/RpViewOptions';
import type { RpLayout } from '../components/resource-planning/GanttRows';
import type { TimelineScale } from '../utils/gantt';
import { AppearanceProvider } from '../contexts/AppearanceContext';
import { useSkin } from '../contexts/ThemeContext';
import { DARK_THEME } from '../utils/constants';
import {
  planStatusTag, useResourcePlanningPage, type ResourcePlanningPageState,
} from '../hooks/useResourcePlanningPage';
import ResourcePlanningZonesLayout from '../skins/zones/pages/ResourcePlanningLayout';

function ResourcePlanningAuroraLayout({ rp }: { rp: ResourcePlanningPageState }) {
  const navigate = useNavigate();
  const {
    planId, viewMode, scale, setScale,
    depDrawMode, blocksOpen, setBlocksOpen,
    showRelayArrows, groupBySubgroup,
    collapsedSections, onToggleSection,
    forkModalOpen, setForkModalOpen, forkLabel, setForkLabel, forkMutation, submitFork, cancelFork,
    setSelectedAssignmentId, selectedAssignment,
    peopleFilter, setPeopleFilter, togglePerson, highlightedEmployeeId,
    appearanceOpen, setAppearanceOpen, appearanceSettings,
    prefs, patchPrefs, layout, setPlanId,
    plansLoading, gantt, ganttLoading, team, blocks, employees,
    subgroupOrder, subgroupByEmployee, candidateEmployees, blockMembers,
    compute, createPlan, handleCompute, handlePickScenario,
    sortedAssignments, sectionByItem, shownAssignments, shownBookings, peopleOptions,
    conflictAssignmentIds, handleToggleCollapse,
    onCreateDependency, onDeleteDependency, onAssignmentChanged,
    currentScenarioId, scenarioOptions,
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
        className="rp-sticky-head"
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
          const { label, color } = planStatusTag(gantt.plan.status);
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
            onClick={() => navigate(`/resource-planning/compare?base=${gantt.plan.parent_plan_id}&scen=${planId}`)}
          >
            Сравнить с базовым
          </Button>
        )}

        {/* Вид диаграммы: частые переключатели на виду, редкие — в окне «Вид». */}
        <Space size={6} style={{ marginLeft: 'auto' }}>
          {viewMode === 'two-level' && gantt && (
            <Segmented
              data-tour="rp-layout-switch"
              size="small"
              value={layout}
              onChange={v => patchPrefs({ view_mode: v as RpLayout })}
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
          onToggleSection={onToggleSection}
          onEmployeeRowClick={togglePerson}
          onCreateDependency={onCreateDependency}
          onDeleteDependency={onDeleteDependency}
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
        onChanged={onAssignmentChanged}
      />

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
  );
}

function ResourcePlanningPageInner() {
  const rp = useResourcePlanningPage();
  const skin = useSkin();
  if (skin === 'zones') return <ResourcePlanningZonesLayout rp={rp} />;
  return <ResourcePlanningAuroraLayout rp={rp} />;
}

export default function ResourcePlanningPage() {
  return (
    <AppearanceProvider>
      <ResourcePlanningPageInner />
    </AppearanceProvider>
  );
}
