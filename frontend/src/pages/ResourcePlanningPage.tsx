import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTeamRegistry } from '../hooks/useTeamRegistry';
import { useSearchParams, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import '../utils/gantt.css';
import { App, Button, Empty, Input, Modal, Select, Segmented, Space, Spin, Switch, Tag } from 'antd';
// Скрытые режимы Портфель/Ресурсы/Plane остаются в коде (PlaneGantt, GanttRows viewMode union)
// PM хочет вернуться к ним после доработки; см. project_resource_planning_modes_hidden.md.
import {
  BgColorsOutlined,
  CalculatorOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import resourcePlanningHelp from '../../../docs/help/resource-planning.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import PlanQualityBadge from '../components/resource-planning/PlanQualityBadge';
import GanttChart from '../components/resource-planning/GanttChart';
import PlaneGantt from '../components/resource-planning/PlaneGantt';
import ConflictPanel from '../components/resource-planning/ConflictPanel';
import ScheduledBlocksModal from '../components/resource-planning/ScheduledBlocksModal';
import AssignmentSidebar from '../components/resource-planning/AssignmentSidebar';
import EmployeeLoadHeatmap from '../components/resource-planning/EmployeeLoadHeatmap';
import AppearanceModal from '../components/resource-planning/AppearanceModal';
import BulkResetDropdown from '../components/resource-planning/BulkResetDropdown';
import type { ViewMode } from '../components/resource-planning/GanttRows';
import {
  useGanttProjection, useResourcePlans, useComputeResourcePlan,
  useScheduledBlocks, useCreateResourcePlan, useForkPlan,
  useCreateDependency, useDeleteDependency,
} from '../hooks/useResourcePlanning';
import { useRpPreferences } from '../hooks/useRpPreferences';
import { useScenarios } from '../hooks/usePlanning';
import type { AssignmentKey, TimelineScale } from '../utils/gantt';
import { findAssignmentByKey } from '../utils/gantt';
import { useEmployees } from '../hooks/useCapacity';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { usePersistedSearchParam } from '../hooks/usePersistedSearchParam';
import { buildSectionByItem, sortBySection } from '../utils/rpSections';
import { sortAssignmentsByScenarioAssignee } from '../utils/sortAssignments';
import { AppearanceProvider, useAppearanceSettings } from '../contexts/AppearanceContext';
import { DARK_THEME } from '../utils/constants';

function ResourcePlanningPageInner() {
  const { message } = App.useApp();
  const [searchParams] = useSearchParams();
  const { selectedTeams } = useGlobalTeamFilter();
  const team = selectedTeams[0] ?? '';

  const navigate = useNavigate();
  const qc = useQueryClient();
  const [planId, setPlanId] = usePersistedSearchParam('plan_id', 'resource_planning_plan_id');
  // Режимы Портфель / Ресурсы / Plane временно скрыты (см. комментарий в шапке файла).
  // Код PlaneGantt и ViewMode union сохранены — переключение вернётся после доработки.
  // Тип расширен до ViewMode чтобы TS не сузил literal — иначе сломаются ветки
  // `viewMode === 'plane'` etc., которые активируются обратно когда переключатель вернётся.
  const viewMode = 'two-level' as ViewMode;
  const [scale, setScale] = useState<TimelineScale>('week');
  const [depDrawMode, setDepDrawMode] = useState(false);
  const [blocksOpen, setBlocksOpen] = useState(false);
  const [showRelayArrows, setShowRelayArrows] = useState(true);
  const [groupBySubgroup, setGroupBySubgroup] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState<string[]>([]);
  const [forkModalOpen, setForkModalOpen] = useState(false);
  const [forkLabel, setForkLabel] = useState('');
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [highlightedEmployeeId, setHighlightedEmployeeId] = useState<string | null>(null);
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  useRegisterHelp('Планирование ресурсов', resourcePlanningHelp);
  const appearanceSettings = useAppearanceSettings();
  const forkMutation = useForkPlan();
  const createDep = useCreateDependency();
  const deleteDep = useDeleteDependency();
  const { prefs, patch: patchPrefs } = useRpPreferences();
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

  const scenarioId = searchParams.get('scenario_id');
  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(team || undefined);
  const { data: approvedScenarios = [] } = useScenarios(undefined, undefined, 'approved', team || undefined);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);
  const { data: blocks = [] } = useScheduledBlocks(team || undefined);
  const { data: allEmployees = [] } = useEmployees({ isActive: true, withTeams: true });
  const employees = team ? allEmployees.filter(e => e.team === team) : allEmployees;

  // Группы внутри команды. План остаётся общекомандным — группы дают только
  // секции строк; занятость человека по-прежнему считается сквозь все группы.
  const { data: teamRegistry = [] } = useTeamRegistry();
  const registryRow = teamRegistry.find(t => t.name === team);
  const subgroupOrder = useMemo(
    () => (registryRow?.has_subgroups ? registryRow.subgroups.map(g => g.name) : []),
    [registryRow],
  );
  const subgroupByEmployee = useMemo(() => {
    if (!registryRow?.has_subgroups || !team) return {};
    const names = new Map(registryRow.subgroups.map(g => [g.id, g.name]));
    const out: Record<string, string> = {};
    for (const e of allEmployees) {
      const membership = e.teams?.find(t => t.team === team);
      const name = membership?.subgroup_id ? names.get(membership.subgroup_id) : undefined;
      out[e.id] = name ?? '';
    }
    return out;
  }, [registryRow, team, allEmployees]);
  // Группа инициативы: своя группа работы, иначе группа её главного
  // исполнителя из сценария (та же логика, что в Сценариях).
  const subgroupNameById = useMemo(
    () => new Map((registryRow?.subgroups ?? []).map(g => [g.id, g.name])),
    [registryRow],
  );

  // Кандидаты в исполнители — состав команды за квартал плана (те же люди,
  // по которым считается загрузка), а не текущий состав на сегодня: выбывший
  // в середине квартала должен оставаться выбираемым на свои дни.
  const candidateEmployees = gantt?.employee_load?.length
    ? gantt.employee_load.map(r => ({
        id: r.employee_id,
        display_name: r.employee_name ?? '—',
        member_from: r.member_from,
        member_to: r.member_to,
      }))
    : employees;
  const compute = useComputeResourcePlan();
  const createPlan = useCreateResourcePlan();

  useEffect(() => {
    if (!scenarioId || plansLoading || createPlan.isPending) return;
    const currentPlan = planId ? plans.find(p => p.id === planId) : null;
    if (currentPlan && currentPlan.scenario_id === scenarioId) return;
    const existing = plans.find(p => p.scenario_id === scenarioId);
    if (existing) {
      setPlanId(existing.id);
      return;
    }
    createPlan.mutateAsync({
      scenario_id: scenarioId,
      team,
      quarter: searchParams.get('quarter') ?? 'Q2',
      year: parseInt(searchParams.get('year') ?? String(new Date().getFullYear())),
    }).then(plan => {
      setPlanId(plan.id);
    }).catch(() => message.error('Ошибка создания плана'));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, planId, plansLoading, plans.length, createPlan.isPending]);

  const handleCompute = async () => {
    if (!planId) return;
    try {
      await compute.mutateAsync(planId);
      message.success('Расписание рассчитано');
    } catch {
      message.error('Ошибка расчёта');
    }
  };

  const handlePickScenario = async (sid: string | null) => {
    if (!sid) {
      setPlanId(null);
      return;
    }
    const existing = plans.find(p => p.scenario_id === sid);
    if (existing) {
      setPlanId(existing.id);
      return;
    }
    const sc = approvedScenarios.find(s => s.id === sid);
    if (!sc || !sc.quarter || !sc.year) {
      message.error('У сценария не задан квартал/год');
      return;
    }
    try {
      const plan = await createPlan.mutateAsync({
        scenario_id: sid,
        team,
        quarter: sc.quarter,
        year: sc.year,
      });
      setPlanId(plan.id);
    } catch {
      message.error('Ошибка создания плана');
    }
  };

  const sortedAssignments = useMemo(
    () => (gantt ? sortAssignmentsByScenarioAssignee(gantt.assignments) : []),
    [gantt],
  );

  // Название группы для каждой инициативы плана.
  const sectionByItem = useMemo(
    () =>
      groupBySubgroup && subgroupOrder.length > 0
        ? buildSectionByItem(sortedAssignments, subgroupNameById, subgroupByEmployee)
        : undefined,
    [groupBySubgroup, subgroupOrder, sortedAssignments, subgroupNameById, subgroupByEmployee],
  );

  const displayedAssignments = useMemo(
    () =>
      sectionByItem
        ? sortBySection(sortedAssignments, sectionByItem, subgroupOrder)
        : sortedAssignments,
    [sortedAssignments, sectionByItem, subgroupOrder],
  );

  const conflictAssignmentIds = useMemo(
    () => (gantt ? gantt.conflicts.flatMap(c => (c.assignment_id ? [c.assignment_id] : [])) : []),
    [gantt],
  );

  // Пересчёт плана пересоздаёт незакреплённые строки с новыми id. Держим
  // логический ключ выбранной фазы и переезжаем на её новую строку, иначе
  // панель остаётся с мёртвым id (404 на расчёте) и молча закрывается.
  const selectedKeyRef = useRef<AssignmentKey | null>(null);

  // Переезд по ключу — прямо в memo, а не в эффекте: иначе между «id устарел»
  // и «id починен» проходит рендер с пустым выбором, и панель успевает
  // закрыться и открыться заново (мигание после смены исполнителя).
  const selectedAssignment = useMemo(() => {
    if (!selectedAssignmentId) return null;
    return (
      sortedAssignments.find(a => a.id === selectedAssignmentId)
      ?? findAssignmentByKey(sortedAssignments, selectedKeyRef.current)
      ?? null
    );
  }, [sortedAssignments, selectedAssignmentId]);

  useEffect(() => {
    if (selectedAssignment) {
      selectedKeyRef.current = {
        backlog_item_id: selectedAssignment.backlog_item_id,
        phase: selectedAssignment.phase,
        part_number: selectedAssignment.part_number,
      };
      if (selectedAssignment.id !== selectedAssignmentId) setSelectedAssignmentId(selectedAssignment.id);
      return;
    }
    if (!selectedAssignmentId) {
      selectedKeyRef.current = null;
      return;
    }
    setSelectedAssignmentId(null);  // фазы больше нет в плане — закрыть панель
  }, [selectedAssignment, selectedAssignmentId]);

  const handleToggleCollapse = (itemId: string, willCollapse: boolean) => {
    const cur = prefs.collapsed_initiative_ids ?? [];
    const next = willCollapse
      ? Array.from(new Set([...cur, itemId]))
      : cur.filter(x => x !== itemId);
    patchPrefs({ collapsed_initiative_ids: next });
  };

  const currentScenarioId = planId
    ? plans.find(p => p.id === planId)?.scenario_id ?? null
    : null;

  const scenarioOptions = approvedScenarios.map(s => ({
    label: `${s.quarter ?? '—'} ${s.year ?? ''} — ${s.name}`,
    value: s.id,
  }));

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
          <Button size="small" onClick={() => setForkModalOpen(true)}>
            Сделать копию
          </Button>
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

        <Space size={4} style={{ marginLeft: 'auto' }}>
          {viewMode === 'two-level' && (
            <Segmented
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
          {viewMode === 'two-level' && (
            <Button
              size="small"
              type={depDrawMode ? 'primary' : 'default'}
              danger={depDrawMode}
              onClick={() => setDepDrawMode(v => !v)}
            >
              {depDrawMode ? 'Связи: ✓' : 'Связи'}
            </Button>
          )}
          {viewMode !== 'resource-track' && (
            <Space size={4}>
              <Switch
                checked={showRelayArrows}
                onChange={setShowRelayArrows}
                size="small"
              />
              <span style={{ fontSize: 12, color: 'var(--text-muted, #8ab0d8)' }}>Эстафета</span>
            </Space>
          )}
          {viewMode === 'two-level' && subgroupOrder.length > 0 && (
            <Button
              size="small"
              type={groupBySubgroup ? 'primary' : 'default'}
              onClick={() => setGroupBySubgroup(v => !v)}
            >
              Группы
            </Button>
          )}
          {viewMode === 'two-level' && (
            <Space size={4}>
              <Switch
                checked={prefs.hide_weekends}
                onChange={(v) => patchPrefs({ hide_weekends: v })}
                size="small"
              />
              <span style={{ fontSize: 12, color: 'var(--text-muted, #8ab0d8)' }}>Только рабочие</span>
            </Space>
          )}
          <Button
            size="small"
            icon={<BgColorsOutlined />}
            onClick={() => setAppearanceOpen(true)}
          >
            Цвета
          </Button>
          {viewMode === 'two-level' && gantt && (
            <Button
              size="small"
              onClick={() => {
                const allIds = Array.from(new Set(gantt.assignments.map(a => a.backlog_item_id)));
                const allCollapsed = (prefs.collapsed_initiative_ids ?? []).length === allIds.length;
                patchPrefs({ collapsed_initiative_ids: allCollapsed ? [] : allIds });
              }}
            >
              {(prefs.collapsed_initiative_ids ?? []).length > 0 ? '↥ Развернуть все' : '↧ Свернуть все'}
            </Button>
          )}
        </Space>
        </div>
      </div>

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
          assignments={displayedAssignments}
          blocks={blocks}
          quarter={gantt.plan.quarter ?? 'Q1'}
          year={gantt.plan.year ?? new Date().getFullYear()}
          viewMode={viewMode}
          showRelayArrows={showRelayArrows}
          planId={planId}
          employees={employees}
          scale={scale}
          dependencies={gantt.dependencies ?? []}
          depDrawMode={depDrawMode}
          collapsedItemIds={prefs.collapsed_initiative_ids}
          onToggleCollapse={handleToggleCollapse}
          conflictAssignmentIds={conflictAssignmentIds}
          onAssignmentClick={(id) => setSelectedAssignmentId(id)}
          hideWeekends={prefs.hide_weekends}
          highlightedEmployeeId={highlightedEmployeeId}
          sectionByItem={sectionByItem}
          subgroupByEmployee={subgroupOrder.length > 0 ? subgroupByEmployee : undefined}
          collapsedSections={collapsedSections}
          onToggleSection={(name, collapsed) =>
            setCollapsedSections(prev =>
              collapsed ? [...prev, name] : prev.filter(n => n !== name),
            )
          }
          onEmployeeRowClick={setHighlightedEmployeeId}
          onCreateDependency={(from, to) => {
            createDep.mutate(
              { planId, fromItemId: from, toItemId: to, depType: 'FS', lagDays: 0 },
              {
                onSuccess: () => message.success('Связь создана'),
                onError: e => message.error((e as Error).message),
              },
            );
          }}
          onDeleteDependency={depId => {
            deleteDep.mutate(
              { planId, depId },
              {
                onSuccess: () => message.success('Связь удалена'),
                onError: e => message.error((e as Error).message),
              },
            );
          }}
        />
      )}

      {gantt?.employee_load && gantt.employee_load.length > 0 && viewMode === 'two-level' && (
        <EmployeeLoadHeatmap
          rows={gantt.employee_load}
          subgroupByEmployee={subgroupOrder.length > 0 ? subgroupByEmployee : undefined}
          subgroupOrder={subgroupOrder}
        />
      )}

      <AssignmentSidebar
        open={!!selectedAssignment}
        onClose={() => setSelectedAssignmentId(null)}
        planId={planId ?? ''}
        assignment={selectedAssignment}
        allAssignments={sortedAssignments}
        employees={candidateEmployees}
        onChanged={() =>
          planId ? qc.invalidateQueries({ queryKey: ['gantt', planId] }) : Promise.resolve()
        }
      />

      <ScheduledBlocksModal open={blocksOpen} onClose={() => setBlocksOpen(false)} team={team || undefined} />

      <Modal
        open={forkModalOpen}
        title="Сделать копию плана"
        okText="Создать"
        cancelText="Отмена"
        onOk={async () => {
          if (!planId) return;
          try {
            const newPlan = await forkMutation.mutateAsync({ planId, label: forkLabel || undefined });
            setForkModalOpen(false);
            setForkLabel('');
            setPlanId(newPlan.id);
            message.success('План скопирован');
          } catch {
            message.error('Ошибка создания копии');
          }
        }}
        onCancel={() => { setForkModalOpen(false); setForkLabel(''); }}
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

export default function ResourcePlanningPage() {
  return (
    <AppearanceProvider>
      <ResourcePlanningPageInner />
    </AppearanceProvider>
  );
}
