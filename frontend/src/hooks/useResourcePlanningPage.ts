import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import resourcePlanningHelp from '../../../docs/help/resource-planning.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import { useTeamRegistry } from './useTeamRegistry';
import type { RpLayout, ViewMode } from '../components/resource-planning/GanttRows';
import {
  useGanttProjection, useResourcePlans, useComputeResourcePlan,
  useScheduledBlocks, useCreateResourcePlan, useForkPlan,
  useCreateDependency, useDeleteDependency, invalidatePlanGantt,
} from './useResourcePlanning';
import { useRpPreferences } from './useRpPreferences';
import { useScenarios } from './usePlanning';
import type { AssignmentKey, TimelineScale } from '../utils/gantt';
import { findAssignmentByKey } from '../utils/gantt';
import { useEmployees } from './useCapacity';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';
import { usePersistedSearchParam } from './usePersistedSearchParam';
import { buildSectionByItem, sortBySection } from '../utils/rpSections';
import { sortAssignmentsByScenarioAssignee } from '../utils/sortAssignments';
import { filterByPeople } from '../utils/rpPeople';
import { decideAutoPlan, groupScenarioOptions, isOutsideHeader, resolvePageTeam } from '../utils/rpTeams';
import { DEFAULT_APPEARANCE, useAppearanceSettings } from '../contexts/AppearanceContext';
import { useAppearance } from '../api/appearance';

/**
 * Данные, состояние и обработчики страницы «Ресурсное планирование» —
 * общие для раскладки Aurora и раскладок обложек. Раскладка только рисует.
 */
export function useResourcePlanningPage() {
  const { message } = App.useApp();
  const [searchParams] = useSearchParams();
  const { selectedTeams } = useGlobalTeamFilter();
  const headerTeams = selectedTeams.join(',') || undefined;

  const navigate = useNavigate();
  const qc = useQueryClient();
  const [planId, setPlanId] = usePersistedSearchParam('plan_id', 'resource_planning_plan_id');
  // Режимы Портфель / Ресурсы / Plane временно скрыты (см. комментарий в шапке страницы).
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
  // Фильтр «Исполнители» — на план: при смене плана сбрасывается, в том числе
  // при возврате к прежнему плану.
  const [peopleFilter, setPeopleFilter] = useState<string[]>([]);
  const [peopleFilterPlanId, setPeopleFilterPlanId] = useState(planId);
  if (peopleFilterPlanId !== planId) {
    setPeopleFilterPlanId(planId);
    setPeopleFilter([]);
  }
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  useRegisterHelp('Планирование ресурсов', resourcePlanningHelp);
  const appearanceSettings = useAppearanceSettings();
  // Окно «Цвета» правит сохранённые цвета, а не подменённые обложкой.
  const appearanceForEditing = useAppearance().data ?? DEFAULT_APPEARANCE;
  const forkMutation = useForkPlan();
  const createDep = useCreateDependency();
  const deleteDep = useDeleteDependency();
  const { prefs, patch: patchPrefs } = useRpPreferences();
  const layout: RpLayout = prefs.view_mode === 'people' ? 'people' : 'tasks';
  // Щелчок по человеку (фишка фазы, имя в подвале, заголовок секции)
  // добавляет его в фильтр или убирает.
  const togglePerson = (id: string | null) => {
    if (!id) return;
    setPeopleFilter(peopleFilter.includes(id) ? peopleFilter.filter(x => x !== id) : [...peopleFilter, id]);
  };
  // Подсветка и пульсация — когда в фильтре ровно один человек.
  const highlightedEmployeeId = peopleFilter.length === 1 ? peopleFilter[0] : null;

  const scenarioId = searchParams.get('scenario_id');
  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(undefined, headerTeams);
  const { data: approvedScenarios = [], isSuccess: scenariosLoaded } = useScenarios(undefined, undefined, 'approved', headerTeams);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);
  // Команда страницы — команда выбранного плана (или сценария из адреса);
  // ничего не выбрано — первая команда шапки.
  const team = resolvePageTeam(
    selectedTeams,
    gantt?.plan.team ?? plans.find(p => p.id === planId)?.team,
    approvedScenarios.find(s => s.id === scenarioId)?.team,
  );
  // Команду убрали из шапки — выбранный план ей больше не принадлежит.
  const planOutside = isOutsideHeader(selectedTeams, gantt?.plan.team);
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
  // Группы сотрудника — из ответа диаграммы (employee_subgroups): список id,
  // по убыванию «доля × дни», первый — главная группа. Не «сегодняшняя»
  // группа из членства — у общих и переведённых людей групп несколько.
  const subgroupByEmployee = useMemo(() => {
    if (!registryRow?.has_subgroups || !gantt?.employee_subgroups) return {};
    const names = new Map(registryRow.subgroups.map(g => [g.id, g.name]));
    const out: Record<string, string[]> = {};
    for (const [empId, groupIds] of Object.entries(gantt.employee_subgroups)) {
      out[empId] = groupIds.map(id => names.get(id)).filter((n): n is string => !!n);
    }
    return out;
  }, [registryRow, gantt]);
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
  // Состав команды для выбора сотрудников заблокированного периода — без привлечённых.
  const blockMembers = useMemo(
    () => (gantt?.employee_load ?? [])
      .filter(r => !r.is_borrowed)
      .map(r => ({ id: r.employee_id, name: r.employee_name ?? '' }))
      .sort((a, b) => a.name.localeCompare(b.name)),
    [gantt],
  );
  const compute = useComputeResourcePlan();
  const createPlan = useCreateResourcePlan();

  useEffect(() => {
    if (planOutside) setPlanId(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planOutside]);

  useEffect(() => {
    if (createPlan.isPending) return;
    const d = decideAutoPlan({
      scenarioId,
      plansLoaded: !plansLoading,
      scenariosLoaded,
      plans,
      scenarios: approvedScenarios,
      currentPlanId: planId,
    });
    if (d.action === 'select') {
      setPlanId(d.planId);
      return;
    }
    if (d.action !== 'create') return;
    createPlan.mutateAsync({
      scenario_id: scenarioId!,
      team: d.team,
      quarter: d.quarter,
      year: d.year,
    }).then(plan => {
      setPlanId(plan.id);
    }).catch(() => message.error('Ошибка создания плана'));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, planId, plansLoading, scenariosLoaded, plans.length, createPlan.isPending]);

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
        team: sc.team ?? team,
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
        ? buildSectionByItem(sortedAssignments, subgroupNameById)
        : undefined,
    [groupBySubgroup, subgroupOrder, sortedAssignments, subgroupNameById],
  );

  const displayedAssignments = useMemo(
    () =>
      sectionByItem
        ? sortBySection(sortedAssignments, sectionByItem, subgroupOrder)
        : sortedAssignments,
    [sortedAssignments, sectionByItem, subgroupOrder],
  );

  // Фильтр по людям: только их фазы и их брони в других командах.
  const shownAssignments = useMemo(
    () => filterByPeople(displayedAssignments, peopleFilter),
    [displayedAssignments, peopleFilter],
  );
  const shownBookings = useMemo(
    () => filterByPeople(gantt?.external_bookings ?? [], peopleFilter),
    [gantt, peopleFilter],
  );
  const peopleOptions = useMemo(
    () => (gantt?.employee_load ?? []).map(r => ({
      value: r.employee_id,
      label: r.is_borrowed
        ? `${r.employee_name ?? '—'} · из ${r.borrowed_from ?? 'другой команды'}`
        : (r.employee_name ?? '—'),
    })),
    [gantt],
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

  const toggleSection = (name: string, collapsed: boolean) =>
    setCollapsedSections(prev =>
      collapsed ? [...prev, name] : prev.filter(n => n !== name),
    );

  const toggleCollapseAll = () => {
    if (!gantt) return;
    const allIds = Array.from(new Set(gantt.assignments.map(a => a.backlog_item_id)));
    const allCollapsed = (prefs.collapsed_initiative_ids ?? []).length === allIds.length;
    patchPrefs({ collapsed_initiative_ids: allCollapsed ? [] : allIds });
  };

  const createDependency = (from: string, to: string) => {
    if (!planId) return;
    createDep.mutate(
      { planId, fromItemId: from, toItemId: to, depType: 'FS', lagDays: 0 },
      {
        onSuccess: () => message.success('Связь создана'),
        onError: e => message.error((e as Error).message),
      },
    );
  };

  const deleteDependency = (depId: string) => {
    if (!planId) return;
    deleteDep.mutate(
      { planId, depId },
      {
        onSuccess: () => message.success('Связь удалена'),
        onError: e => message.error((e as Error).message),
      },
    );
  };

  const submitFork = async () => {
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
  };

  const cancelFork = () => { setForkModalOpen(false); setForkLabel(''); };

  const refreshGantt = () => (planId ? invalidatePlanGantt(qc, planId) : Promise.resolve());

  const openCompare = () => {
    if (gantt?.plan.parent_plan_id) {
      navigate(`/resource-planning/compare?base=${gantt.plan.parent_plan_id}&scen=${planId}`);
    }
  };

  const currentScenarioId = planId
    ? plans.find(p => p.id === planId)?.scenario_id ?? null
    : null;

  const scenarioOptions = groupScenarioOptions(approvedScenarios, selectedTeams);

  return {
    planId, setPlanId, viewMode, scale, setScale,
    depDrawMode, setDepDrawMode, blocksOpen, setBlocksOpen,
    showRelayArrows, setShowRelayArrows, groupBySubgroup, setGroupBySubgroup,
    collapsedSections, toggleSection,
    forkModalOpen, setForkModalOpen, forkLabel, setForkLabel, forkMutation, submitFork, cancelFork,
    selectedAssignmentId, setSelectedAssignmentId, selectedAssignment,
    peopleFilter, setPeopleFilter, peopleOptions, togglePerson, highlightedEmployeeId,
    appearanceOpen, setAppearanceOpen, appearanceSettings, appearanceForEditing,
    prefs, patchPrefs, layout,
    plans, plansLoading, approvedScenarios, gantt, ganttLoading,
    team, blocks, employees, candidateEmployees, blockMembers,
    subgroupOrder, subgroupByEmployee,
    compute, createPlan, handleCompute, handlePickScenario,
    sortedAssignments, sectionByItem, shownAssignments, shownBookings, conflictAssignmentIds,
    handleToggleCollapse, toggleCollapseAll, createDependency, deleteDependency,
    refreshGantt, openCompare, currentScenarioId, scenarioOptions,
  };
}

export type ResourcePlanningPageState = ReturnType<typeof useResourcePlanningPage>;
