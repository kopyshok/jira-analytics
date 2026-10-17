import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import type { DragEndEvent } from '@dnd-kit/core';
import { App } from 'antd';
import planningHelp from '../../../docs/help/planning.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import { useOpoCutoff } from './useOpoCutoff';
import { useScenarioContinuationInfo } from './useScenarioContinuationInfo';
import {
  useScenarios,
  useScenario,
  useScenarioAllocations,
  usePatchAllocation,
  useDeleteScenario,
  useApproveScenario,
  useRevertScenario,
  useScenarioResource,
  useScenarioResourceSummary,
  useUpdateScenario,
  usePatchAllocationAssignee,
  usePatchAllocationDeveloper,
  useSetAllocationSubgroup,
  useReorderAllocations,
  usePatchBacklogPriority,
} from './usePlanning';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';
import { useAppearance, useUpdateAppearance } from '../api/appearance';
import { DEFAULT_APPEARANCE } from '../contexts/appearanceDefaults';
import { useGlobalPeriod } from './useGlobalPeriod';
import { usePersistedSearchParam } from './usePersistedSearchParam';
import { trackAction } from '../lib/usage/track';
import { useRoles } from './useRoles';
import { useJiraBaseUrl } from './useSettings';
import { computeDeficitByRole, demandByAssigneeRole, demandByRole } from '../utils/planning';
import { effectiveEstimate } from '../utils/allocationEstimates';
import { sortByPerson, type PersonSort } from '../utils/allocationSort';
import { neighborsTakenRowIds } from '../utils/multiTeamProgress';
import type { AllocationResponse } from '../types/api';

export const GRID = '24px 36px 60px minmax(220px, 1fr) 130px 130px 180px 260px 90px';
// Та же сетка + колонка «Группа» после разработчика — для команд с делением.
export const GRID_WITH_SUBGROUP = '24px 36px 60px minmax(220px, 1fr) 130px 130px 140px 180px 260px 90px';
export const GRID_GAP = 8;
// Уже этой ширины список прокручивается вбок, а не сжимает «Идею» до нуля:
// колонки (у «Идеи» — её минимум) + зазоры + поля строки и полоса отметки слева.
export const gridMinWidth = (tpl: string) => {
  const px = [...tpl.matchAll(/(\d+)px/g)].map((m) => Number(m[1]));
  return px.reduce((sum, w) => sum + w, 0) + (px.length - 1) * GRID_GAP + 32;
};


export function rolesAffectedByAllocation(
  a: AllocationResponse,
  employees: { employee_id: string; role: string | null }[] | undefined,
): string[] {
  const eff = effectiveEstimate(a);
  const ea = eff.analyst;
  const ed = eff.dev;
  const eq = eff.qa;
  const eo = eff.opo;
  const r = a.opo_analyst_ratio ?? 0.5;
  const emp = employees?.find((e) => e.employee_id === a.assignee_employee_id);
  const role = emp?.role ?? a.assignee_role ?? null;
  const isAnalystSubstitute =
    role === 'RP' || role === 'project_manager' || role === 'consultant';
  const analystTarget = isAnalystSubstitute ? (role as string) : 'analyst';
  const out: string[] = [];
  if (ea + eo * r > 0) out.push(analystTarget);
  if (ed + eo * (1 - r) > 0) out.push('dev');
  if (eq > 0) out.push('qa');
  return out;
}

/**
 * Данные, отметки и обработчики раздела «Сценарии» — общие для раскладки
 * Aurora и раскладок скинов. Раскладка только рисует.
 */
export function usePlanningPage() {
  const { notification } = App.useApp();
  const navigate = useNavigate();
  const [scenarioId, setScenarioId] = usePersistedSearchParam('scenario', 'planning_scenario_id');
  const [createOpen, setCreateOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'distribution' | 'rules'>('distribution');
  const [celebrate, setCelebrate] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [involvementOpen, setInvolvementOpen] = useState(false);
  const [ungroupedDrawerId, setUngroupedDrawerId] = useState<string | null>(null);
  useRegisterHelp('Планирование сценариев', planningHelp);
  // Компактный режим — всегда включён; тумблер выпилен по запросу PM.
  const compact = true;

  const [flashingIds, setFlashingIds] = useState<Set<string>>(() => new Set());

  const flashRow = (allocId: string) => {
    setFlashingIds((prev) => {
      const next = new Set(prev);
      next.add(allocId);
      return next;
    });
    setTimeout(() => {
      setFlashingIds((prev) => {
        const next = new Set(prev);
        next.delete(allocId);
        return next;
      });
    }, 650);
  };

  const [pulsedRoles, setPulsedRoles] = useState<Set<string>>(() => new Set());

  const pulseRoles = (roles: string[]) => {
    if (roles.length === 0) return;
    setPulsedRoles((prev) => {
      const next = new Set(prev);
      roles.forEach((r) => next.add(r));
      return next;
    });
    setTimeout(() => {
      setPulsedRoles((prev) => {
        const next = new Set(prev);
        roles.forEach((r) => next.delete(r));
        return next;
      });
    }, 600);
  };

  const { data: roles = [] } = useRoles();
  const jiraSettings = useJiraBaseUrl();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';
  const { queryParams } = useGlobalTeamFilter();
  const { period } = useGlobalPeriod();
  const [breakdown, setBreakdown] = useState<{ open: boolean; issueId: string | null; issueKey: string }>({
    open: false, issueId: null, issueKey: '',
  });
  const { data: scenarios } = useScenarios(undefined, undefined, undefined, queryParams.teams);
  const { data: scenario } = useScenario(scenarioId);
  const { opoOffFor } = useOpoCutoff();
  const opoOff = opoOffFor(scenario?.year, scenario?.quarter);
  const { data: allocations, isLoading: allocLoading } =
    useScenarioAllocations(scenarioId);
  const { data: continuation } = useScenarioContinuationInfo(scenarioId ?? undefined);

  // Берём только mutate: сам объект мутации пересоздаётся на каждый рендер и
  // ломал бы мемоизацию строк через колбэки ниже.
  const { mutate: patchAlloc } = usePatchAllocation();
  // Поднимать ли включённую задачу наверх — личная настройка пользователя.
  const appearance = useAppearance();
  const updateAppearance = useUpdateAppearance();
  const appearanceValue = appearance.data ?? DEFAULT_APPEARANCE;
  const liftIncluded = appearanceValue.scenario_lift_included;
  const { mutate: patchAssignee } = usePatchAllocationAssignee();
  const { mutate: patchDeveloper } = usePatchAllocationDeveloper();
  const { mutateAsync: patchBacklogPriority } = usePatchBacklogPriority();
  const updateScenario = useUpdateScenario();
  const deleteScenario = useDeleteScenario();
  const approve = useApproveScenario();
  const revert = useRevertScenario();

  // Запоминаем id, который сейчас удаляется, — иначе авто-выбор ниже успеет
  // снова взять его из стейл-кэша списка между `setScenarioId(null)` и
  // refetch'ем, и лечит 404 на useScenario/useScenarioAllocations.
  const deletingIdRef = useRef<string | null>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // Авто-выбор: если сценарий из URL исчез (удалили) либо не выбран — взять
  // первый доступный, кроме того, что сейчас в процессе удаления.
  useEffect(() => {
    if (!scenarios) return;
    const available = scenarios.filter((s) => s.id !== deletingIdRef.current);
    if (scenarioId && !available.some((s) => s.id === scenarioId)) {
      setScenarioId(available[0]?.id ?? null);
      return;
    }
    if (!scenarioId && available.length > 0) {
      setScenarioId(available[0].id);
    }
  }, [scenarioId, scenarios]); // eslint-disable-line react-hooks/exhaustive-deps

  const includedIds = useMemo(
    () => (allocations ?? []).filter((a) => a.included).map((a) => a.backlog_item_id),
    [allocations],
  );

  // Порядок строк — целиком с бэка (sort_order). Чек поднимает строку
  // наверх, снятие — оставляет на месте, drag&drop переписывает порядок.
  const orderedAllocations = useMemo(() => allocations ?? [], [allocations]);

  // FLIP-анимация перестановок: меряем top всех строк по data-alloc-id
  // ДО render'а (useLayoutEffect возвращает функцию, она НЕ для cleanup —
  // она вызывается перед следующим эффектом). Лучше: ref хранит prev positions,
  // обновляем после применения инверсии.

  const flipPrevTopsRef = useRef<Map<string, number>>(new Map());
  const allocIdsKey = orderedAllocations.map((a) => a.id).join(',');

  // Шаг 1 (useLayoutEffect): СРАВНИВАЕМ текущий top с сохранённым prev,
  // если есть строка с большой delta — анимируем её FLIP-инверсией.
  // Шаг 2 (useEffect): после paint обновляем prev на текущие top'ы.
  // Этот двух-фазный паттерн нужен потому что useLayoutEffect срабатывает
  // ПОСЛЕ commit'а DOM с новым порядком — top уже новый, prev должен быть старым.
  useLayoutEffect(() => {
    const rows = document.querySelectorAll<HTMLElement>('[data-flip-wrapper]');
    const prev = flipPrevTopsRef.current;
    let maxDelta = 0;
    let mainId: string | null = null;
    const nextTops = new Map<string, number>();
    rows.forEach((el) => {
      const id = el.dataset.allocId!;
      const cur = el.getBoundingClientRect().top;
      nextTops.set(id, cur);
      const prevTop = prev.get(id);
      if (prevTop !== undefined) {
        const abs = Math.abs(prevTop - cur);
        if (abs > maxDelta) { maxDelta = abs; mainId = id; }
      }
    });
    if (mainId && maxDelta > 5) {
      const el = document.querySelector<HTMLElement>(`[data-flip-wrapper][data-alloc-id="${mainId}"]`);
      if (el) {
        const prevTop = prev.get(mainId)!;
        const cur = nextTops.get(mainId)!;
        const delta = prevTop - cur;
        // Ставим инверсию без transition.
        el.style.transition = 'none';
        el.style.transform = `translate3d(0, ${delta}px, 0)`;
        // Ждём ДВА rAF (один для применения inversion, второй для гарантии браузерного paint).
        // void offsetHeight (force reflow) недостаточно — браузер всё равно
        // объединит установку инверсии и установку 0 в один paint, если они в одном тике.
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            el.style.transition = 'transform 1500ms cubic-bezier(0.22, 1, 0.36, 1)';
            el.style.transform = 'translate3d(0, 0, 0)';
            // transitionend bubbles up от child'ов (AntD checkbox/tag и т.д.)
            // — фильтруем по target и propertyName, иначе cleanup стрельнёт раньше.
            const cleanup = (ev: TransitionEvent) => {
              if (ev.target !== el || ev.propertyName !== 'transform') return;
              el.style.transition = '';
              el.style.transform = '';
              el.removeEventListener('transitionend', cleanup);
            };
            el.addEventListener('transitionend', cleanup);
          });
        });
      }
    }
    // Обновляем prev ТОЛЬКО ПОСЛЕ анимации (или сразу если ничего не анимировали),
    // чтобы следующий reorder сравнивался с актуальными «до» позициями.
    flipPrevTopsRef.current = nextTops;
  }, [allocIdsKey]);

  // Стабильные ссылки для мемоизированных строк: новый массив на каждый рендер
  // дёргал бы dnd-контекст и пересобирал выпадающий список в каждой строке.
  const reorderAllocs = useReorderAllocations();
  // Сортировка по людям — только вид на экране: порядок строк на сервере не меняется.
  const [personSort, setPersonSort] = useState<PersonSort | null>(null);
  const handleDragEnd = ({ active: dragActive, over }: DragEndEvent) => {
    if (!scenarioId || !isDraft || personSort) return;
    if (!over || dragActive.id === over.id) return;
    const ids = orderedAllocations.map((a) => a.id);
    const oldIndex = ids.indexOf(String(dragActive.id));
    const newIndex = ids.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    // Перетаскивание живёт внутри своей группы: группа меняется выпадашкой,
    // а не броском строки — иначе один жест значит две разные вещи.
    if (
      (orderedAllocations[oldIndex].subgroup_id ?? '') !==
      (orderedAllocations[newIndex].subgroup_id ?? '')
    ) {
      return;
    }
    const next = ids.slice();
    next.splice(oldIndex, 1);
    next.splice(newIndex, 0, String(dragActive.id));
    reorderAllocs.mutate({ scenarioId, orderedIds: next });
  };

  const quarterInt = useMemo(() => {
    if (!scenario?.quarter) return 0;
    const m = scenario.quarter.match(/Q(\d)/);
    return m ? Number(m[1]) : 0;
  }, [scenario]);

  // Ресурс команды — не зависит от конкретных включённых идей, грузится один раз.
  // Не дёргаем ручку пока у сценария не выбрана команда — иначе бэк вернёт 400.
  const { data: resourceBase } = useScenarioResource(
    scenarioId ?? undefined,
    !!scenario?.team,
  );

  const { data: resourceSummary } = useScenarioResourceSummary(
    scenarioId ?? '',
    !!scenario?.team,
  );

  // Запасной список исполнителя строки — состав команды сценария: если список
  // кандидатов из всех команд не загрузился, выбрать всё равно есть из кого.
  const teamAssigneeOptions = useMemo(
    () => (resourceBase?.employees ?? []).map((emp) => ({
      label: emp.display_name,
      value: emp.employee_id,
    })),
    [resourceBase?.employees],
  );

  const isDraft = scenario?.status === 'draft';
  const isApproved = scenario?.status === 'approved';

  const deficit = useMemo(() => {
    if (!resourceSummary || !allocations) return {};
    const demand =
      resourceBase?.employees && resourceBase.employees.length > 0
        ? demandByAssigneeRole(allocations, resourceBase.employees)
        : demandByRole(allocations);
    return computeDeficitByRole(resourceSummary.available_for_backlog_by_role, demand);
  }, [resourceSummary, allocations, resourceBase]);

  const hasAnyDeficit = Object.keys(deficit).length > 0;

  const rowStateClass = (a: AllocationResponse): string => {
    const eff = effectiveEstimate(a);
    const total = eff.analyst + eff.dev + eff.qa + eff.opo;
    if (total <= 0) return 'row-state-no-estimates';
    if (a.included && hasAnyDeficit) return 'row-state-deficit';
    if (a.source_category === 'quarterly_tasks') return 'row-state-in-work';
    return '';
  };

  const scrollRowIntoView = (allocId: string) => {
    const el = rowRefs.current.get(allocId);
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const fullyVisible = rect.top >= 60 && rect.bottom <= window.innerHeight - 20;
    if (!fullyVisible) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  const toggleAllocation = useCallback(
    (alloc: AllocationResponse) => {
      if (!scenarioId || !isDraft) return;
      flashRow(alloc.id);
      pulseRoles(rolesAffectedByAllocation(alloc, resourceBase?.employees));
      scrollRowIntoView(alloc.id);
      patchAlloc(
        {
          scenarioId,
          allocId: alloc.id,
          // Подъём строки наверх — личная настройка: кто его выключил,
          // у того включённая задача остаётся на своём месте.
          data: { included: !alloc.included, lift: liftIncluded },
        },
        { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
      );
    },
    [scenarioId, isDraft, resourceBase?.employees, patchAlloc, notification, liftIncluded],
  );

  const registerRowRef = useCallback((id: string, el: HTMLDivElement | null) => {
    if (el) rowRefs.current.set(id, el);
    else rowRefs.current.delete(id);
  }, []);

  const handlePriorityChange = useCallback(
    (backlogItemId: string, priority: number | null) => {
      return patchBacklogPriority({ backlogItemId, priority });
    },
    [patchBacklogPriority],
  );

  const handleAssigneeChange = useCallback(
    (allocId: string, employeeId: string | null) => {
      if (!scenarioId) return;
      patchAssignee({ scenarioId, allocId, assigneeEmployeeId: employeeId });
    },
    [patchAssignee, scenarioId],
  );

  const handleDeveloperChange = useCallback(
    (allocId: string, employeeId: string | null) => {
      if (!scenarioId) return;
      patchDeveloper({ scenarioId, allocId, developerEmployeeId: employeeId });
    },
    [patchDeveloper, scenarioId],
  );

  // === Группы внутри команды =============================================
  // Список групп приходит вместе со сводкой ресурса. Пусто — у команды нет
  // деления, и раздел выглядит ровно как до правки.
  const subgroups = useMemo(() => resourceSummary?.subgroups ?? [], [resourceSummary]);
  const hasSubgroups = subgroups.length > 0;
  const ungrouped = resourceSummary?.ungrouped_employees ?? [];
  const subgroupOptions = useMemo(
    () => subgroups.map((g) => ({ label: g.name, value: g.id })),
    [subgroups],
  );
  const subgroupOfAlloc = useCallback(
    (a: AllocationResponse) => a.subgroup_id ?? '',
    [],
  );

  const sections = useMemo(() => {
    if (!hasSubgroups) {
      return [{ id: null as string | null, name: '', items: sortByPerson(orderedAllocations, personSort) }];
    }
    const byGroup = new Map<string, AllocationResponse[]>();
    for (const a of orderedAllocations) {
      const key = subgroupOfAlloc(a);
      const bucket = byGroup.get(key);
      if (bucket) bucket.push(a);
      else byGroup.set(key, [a]);
    }
    const out = subgroups
      .map((g) => ({
        id: g.id as string | null,
        name: g.name,
        items: sortByPerson(byGroup.get(g.id) ?? [], personSort),
      }))
      .filter((sec) => sec.items.length > 0);
    const orphans = byGroup.get('');
    if (orphans?.length) out.push({ id: '', name: 'Без группы', items: sortByPerson(orphans, personSort) });
    return out;
  }, [hasSubgroups, subgroups, orderedAllocations, subgroupOfAlloc, personSort]);

  // Мультикомандные RFA: соседние команды уже взяли задачу, а здесь она не
  // включена. «Показать только их» оставляет в секциях только такие строки.
  // Только в черновике — в утверждённом отметки не поменять. Переключатель
  // помнит свой сценарий: другой сценарий открывается без фильтра.
  const neighborsTakenIds = useMemo(
    () => (isDraft ? neighborsTakenRowIds(allocations ?? []) : new Set<string>()),
    [isDraft, allocations],
  );
  const [onlyNeighborsFor, setOnlyNeighborsFor] = useState<string | null>(null);
  const onlyNeighborsTaken = !!scenarioId && onlyNeighborsFor === scenarioId;
  const shownSections = useMemo(() => {
    if (!onlyNeighborsTaken || neighborsTakenIds.size === 0) return sections;
    return sections
      .map((sec) => ({ ...sec, items: sec.items.filter((a) => neighborsTakenIds.has(a.id)) }))
      .filter((sec) => sec.items.length > 0);
  }, [sections, onlyNeighborsTaken, neighborsTakenIds]);

  // Свёрнутые секции живут в браузере — у каждого планировщика свои.
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem('planning.collapsedSubgroups');
      return new Set<string>(raw ? JSON.parse(raw) : []);
    } catch {
      return new Set<string>();
    }
  });
  const toggleSection = useCallback((id: string) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        localStorage.setItem('planning.collapsedSubgroups', JSON.stringify([...next]));
      } catch {
        // приватный режим браузера — просто не запоминаем
      }
      return next;
    });
  }, []);

  const setSubgroup = useSetAllocationSubgroup();
  const handleSubgroupChange = useCallback(
    (issueId: string, subgroupId: string | null) => {
      if (!scenarioId) return;
      setSubgroup.mutate({ scenarioId, issueId, subgroupId });
    },
    [setSubgroup, scenarioId],
  );

  const handleOpenBreakdown = useCallback((issueId: string, issueKey: string) => {
    setBreakdown({ open: true, issueId, issueKey });
  }, []);

  const handleApprove = () => {
    if (!scenarioId) return;
    approve.mutate(scenarioId, {
      onSuccess: () => {
        trackAction('scenario_approved', scenarioId);
        setCelebrate(true);
        setTimeout(() => setCelebrate(false), 1700);
        notification.success({ title: 'Сценарий утверждён' });
      },
      onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const handleRevert = () => {
    if (!scenarioId) return;
    revert.mutate(scenarioId, {
      onSuccess: () => notification.success({ title: 'Возвращено в черновик' }),
      onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const handleDelete = () => {
    if (!scenarioId) return;
    const id = scenarioId;
    deletingIdRef.current = id;
    setScenarioId(null);
    deleteScenario.mutate(id, {
      onSuccess: () => {
        notification.success({ title: 'Сценарий удалён' });
        deletingIdRef.current = null;
      },
      onError: (e) => {
        deletingIdRef.current = null;
        notification.error({ title: 'Ошибка', description: (e as Error).message });
      },
    });
  };

  const handleTeamChange = (team: string | null) => {
    if (!scenarioId) return;
    updateScenario.mutate(
      { id: scenarioId, data: { team } },
      { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
    );
  };

  // Enter/потеря фокуса — сохранить; Esc AntD отменяет сам. Пустое и
  // неизменённое имя не отправляем. Разрешено и для утверждённого сценария.
  const handleRename = (next: string) => {
    const name = next.trim();
    if (!scenarioId || !name || name === scenario?.name) return;
    updateScenario.mutate(
      { id: scenarioId, data: { name } },
      { onError: (e) => notification.error({ title: 'Не удалось переименовать', description: (e as Error).message }) },
    );
  };

  const scenarioOptions = useMemo(
    () => (scenarios ?? []).map((s) => ({
      value: s.id,
      label: `${s.name} · ${s.quarter ?? ''} ${s.year ?? ''}${s.status === 'approved' ? ' ✓' : ''}`,
    })),
    [scenarios],
  );

  return {
    navigate,
    scenarioId,
    setScenarioId,
    createOpen,
    setCreateOpen,
    activeTab,
    setActiveTab,
    celebrate,
    diffOpen,
    setDiffOpen,
    compareOpen,
    setCompareOpen,
    historyOpen,
    setHistoryOpen,
    involvementOpen,
    setInvolvementOpen,
    ungroupedDrawerId,
    setUngroupedDrawerId,
    compact,
    flashingIds,
    pulsedRoles,
    roles,
    jiraBaseUrl,
    period,
    breakdown,
    setBreakdown,
    scenario,
    opoOff,
    allocations,
    allocLoading,
    continuation,
    appearanceValue,
    liftIncluded,
    updateAppearance,
    approve,
    revert,
    includedIds,
    personSort,
    setPersonSort,
    handleDragEnd,
    quarterInt,
    resourceBase,
    resourceSummary,
    teamAssigneeOptions,
    isDraft,
    isApproved,
    deficit,
    rowStateClass,
    toggleAllocation,
    registerRowRef,
    handlePriorityChange,
    handleAssigneeChange,
    handleDeveloperChange,
    hasSubgroups,
    ungrouped,
    subgroupOptions,
    neighborsTakenIds,
    onlyNeighborsTaken,
    setOnlyNeighborsFor,
    shownSections,
    collapsedSections,
    toggleSection,
    handleSubgroupChange,
    handleOpenBreakdown,
    handleApprove,
    handleRevert,
    handleDelete,
    handleTeamChange,
    handleRename,
    scenarioOptions,
  };
}

export type PlanningPageState = ReturnType<typeof usePlanningPage>;
