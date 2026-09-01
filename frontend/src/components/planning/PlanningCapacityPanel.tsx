import { memo, useMemo, useState } from 'react';
import { Card, Select, Skeleton, Tag, Tooltip } from 'antd';
import { DownOutlined, RightOutlined } from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { DARK_THEME, FONTS } from '../../utils/constants';
import { useRoles } from '../../hooks/useRoles';
import { getRoleColor } from '../../utils/roles';
import type { AllocationResponse, ResourceBase, ResourceEmployee, ResourceSummaryOut } from '../../types/api';
import RoleCapacityBar from './RoleCapacityBar';
import { patchEmployee } from '../../api/employees';
import { demandByAssigneeRole } from '../../utils/planning';
import { effectiveEstimate } from '../../utils/allocationEstimates';

const CORE_ROLE_KEYS = ['analyst', 'dev', 'qa'] as const;
type CoreRoleKey = (typeof CORE_ROLE_KEYS)[number];

const ROLE_SORT_ORDER: string[] = ['RP', 'analyst', 'dev', 'qa', 'consultant', 'other'];
const roleSortKey = (role: string | null | undefined): number => {
  if (!role) return ROLE_SORT_ORDER.length + 1;
  const idx = ROLE_SORT_ORDER.indexOf(role);
  return idx === -1 ? ROLE_SORT_ORDER.length : idx;
};

const ROLE_SHORT_LOCAL: Record<string, string> = {
  analyst: 'АН',
  dev: 'ПР',
  qa: 'ТС',
  consultant: 'КН',
  RP: 'РП',
  other: 'ДР',
};

interface Props {
  resourceBase: ResourceBase | undefined;
  allocations: AllocationResponse[];
  quarter: string;
  scenarioId: string;
  summary?: ResourceSummaryOut;
}

function getRoleShort(role: string): string {
  return ROLE_SHORT_LOCAL[role] ?? role.slice(0, 2).toUpperCase();
}


function PlanningCapacityPanelBase({ resourceBase, summary, allocations, quarter, scenarioId }: Props) {
  const { data: roles = [] } = useRoles();
  const qc = useQueryClient();
  const setRoleMutation = useMutation({
    mutationFn: ({ employeeId, role }: { employeeId: string; role: string }) =>
      patchEmployee(employeeId, { role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['planning', 'scenario', scenarioId, 'resource'] });
      qc.invalidateQueries({ queryKey: ['employees'] });
    },
  });

  // Персональная нагрузка ответственного: каждому ассайни — часы только его
  // типа работ (аналитик/dev/qa). РП, project_manager и Консультант
  // «закрывают» аналитическую часть. Часы dev/qa других типов работ
  // одной и той же задачи в персональный счёт не попадают — они уходят в
  // соответствующие ролевые пулы (см. demandByRole ниже).
  const demandByEmployee = useMemo(() => {
    const result: Record<string, number> = {};
    for (const alloc of allocations) {
      if (!alloc.included) continue;
      let emp = alloc.assignee_employee_id
        ? resourceBase?.employees.find((e) => e.employee_id === alloc.assignee_employee_id)
        : undefined;
      // Фолбэк: если у задачи нет связки employee_id, но есть display_name
      // (бывает, когда бэклог подтянул задачу из Jira без смапленного Employee),
      // ищем сотрудника по имени в команде сценария. Сопоставление толерантное:
      // сравниваем множества слов — порядок и лишние слова не мешают
      // («Копышков Николай» ↔ «Копышков Николай Сергеевич»).
      if (!emp && alloc.assignee_display_name) {
        const tokens = (s: string) =>
          new Set(s.toLowerCase().split(/\s+/).filter((t) => t.length >= 3));
        const need = tokens(alloc.assignee_display_name);
        if (need.size > 0) {
          emp = resourceBase?.employees.find((e) => {
            const have = tokens(e.display_name);
            let hit = 0;
            for (const t of need) if (have.has(t)) hit += 1;
            return hit >= Math.min(2, need.size);
          });
        }
      }
      if (!emp?.role) continue;
      const eff = effectiveEstimate(alloc);
      const r = alloc.opo_analyst_ratio ?? 0.5;
      const role = emp.role;
      const personalLoad =
        role === 'analyst' ||
        role === 'RP' ||
        role === 'project_manager' ||
        role === 'consultant'
          ? eff.analyst + eff.opo * r
          : role === 'dev'
            ? eff.dev + eff.opo * (1 - r)
            : role === 'qa'
              ? eff.qa
              : 0;
      result[emp.employee_id] = (result[emp.employee_id] ?? 0) + personalLoad;
    }
    return result;
  }, [allocations, resourceBase]);

  // Потребность по ролям: часы каждого типа работ всегда падают в свой пул
  // (analyst / dev / qa) независимо от ответственного. Используем общую
  // утилиту, чтобы поведение совпадало с расчётом дефицита на странице
  // «Сценарии» и в карточке «Сводка по ресурсу».
  const demandByEmployeeRole = useMemo(
    () =>
      resourceBase?.employees
        ? demandByAssigneeRole(allocations, resourceBase.employees)
        : ({} as Record<string, number>),
    [allocations, resourceBase],
  );

  // === Разрез по группам внутри команды =================================
  // Пустой список групп — деления нет, карточки выглядят как раньше.
  const subgroups = useMemo(() => summary?.subgroups ?? [], [summary]);
  const hasSubgroups = subgroups.length > 0;

  // Потребность по ролям внутри каждой группы: та же утилита, что для команды,
  // но на идеях этой группы.
  const demandBySubgroupRole = useMemo(() => {
    const out: Record<string, Record<string, number>> = {};
    if (!hasSubgroups || !resourceBase?.employees) return out;
    const byGroup: Record<string, AllocationResponse[]> = {};
    for (const a of allocations) {
      const key = a.subgroup_id ?? '';
      (byGroup[key] ??= []).push(a);
    }
    for (const [key, list] of Object.entries(byGroup)) {
      out[key] = demandByAssigneeRole(list, resourceBase.employees);
    }
    return out;
  }, [hasSubgroups, allocations, resourceBase]);

  const [collapsedRoleGroups, setCollapsedRoleGroups] = useState<Set<string>>(new Set());
  const [collapsedEmpGroups, setCollapsedEmpGroups] = useState<Set<string>>(new Set());

  if (!resourceBase) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Card><Skeleton active paragraph={{ rows: 3 }} /></Card>
        <Card><Skeleton active paragraph={{ rows: 4 }} /></Card>
        <Card><Skeleton active paragraph={{ rows: 5 }} /></Card>
      </div>
    );
  }

  // Для ролевых баров: используем available_for_backlog_by_role из summary (после вычета обяз. работ).
  // Если summary ещё не загружен — fallback на role_totals из resourceBase.
  const availableByRole: Record<string, number> = summary
    ? { ...summary.available_for_backlog_by_role }
    : { ...resourceBase.role_totals };

  // Для qa берём то же значение, что и верхняя таблица в строке «На бэклог»
  // (норма минус обязательные работы). Раньше здесь подставлялись валовые
  // часы внешнего тестировщика без вычета обяз. работ — правый блок
  // показывал 680, а верхняя таблица 340.
  const capacityByRole: Record<CoreRoleKey, number> = {
    analyst: availableByRole['analyst'] ?? 0,
    dev:     availableByRole['dev']     ?? 0,
    qa:      availableByRole['qa']      ?? 0,
  };

  const infoRoles = roles.filter(
    (r) => r.counts_in_planning && !(CORE_ROLE_KEYS as readonly string[]).includes(r.code),
  );

  const totalCapacity = Object.values(capacityByRole).reduce((s, v) => s + v, 0)
    + infoRoles.reduce((s, r) => s + (availableByRole[r.code] ?? 0), 0);
  const totalDemand = Object.values(demandByEmployeeRole).reduce((s, v) => s + v, 0);
  const overallOver = Object.entries(demandByEmployeeRole).some(
    ([role, d]) => d > (availableByRole[role] ?? 0) && (availableByRole[role] ?? 0) > 0,
  );
  const freeHours = Math.max(0, Math.round(totalCapacity - totalDemand));
  const freePct = totalCapacity > 0
    ? Math.max(0, Math.round((1 - totalDemand / totalCapacity) * 100))
    : 0;
  const plannedPct = totalCapacity > 0
    ? Math.min(100, (totalDemand / totalCapacity) * 100)
    : 0;

  const includedCount = allocations.filter((a) => a.included).length;

  // Обязательные работы по роли из summary для подписи сотрудников
  const mandatoryPctByRole: Record<string, number> = {};
  if (summary) {
    for (const row of summary.work_type_rows) {
      if (!row.subtracts_from_pool) continue;
      for (const role of summary.roles) {
        const pct = row.by_role_pct[role];
        if (pct != null) {
          mandatoryPctByRole[role] = (mandatoryPctByRole[role] ?? 0) + pct;
        }
      }
    }
  }

  // Секции групп: сотрудники группы + её ёмкость по ролям. «Без группы» —
  // последней и только если в ней кто-то есть.
  const groupSections = hasSubgroups
    ? [
        ...subgroups.map((g) => ({
          id: g.id,
          name: g.name,
          employees: resourceBase.employees.filter((e) => (e.subgroup_id ?? '') === g.id),
        })),
        ...(resourceBase.employees.some((e) => !e.subgroup_id)
          ? [
              {
                id: '',
                name: 'Без группы',
                employees: resourceBase.employees.filter((e) => !e.subgroup_id),
              },
            ]
          : []),
      ]
    : [];

  const sectionHeader = (
    name: string,
    right: string,
    collapsed: boolean,
    onToggle: () => void,
  ) => (
    <div
      onClick={onToggle}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 14px',
        cursor: 'pointer',
        background: DARK_THEME.darkAccent,
        borderTop: `1px solid ${DARK_THEME.border}`,
        userSelect: 'none',
      }}
    >
      {collapsed ? (
        <RightOutlined style={{ fontSize: 10, color: DARK_THEME.textMuted }} />
      ) : (
        <DownOutlined style={{ fontSize: 10, color: DARK_THEME.textMuted }} />
      )}
      <span style={{ fontSize: 13, fontWeight: 600, color: DARK_THEME.textPrimary }}>{name}</span>
      <span style={{ flex: 1 }} />
      <span style={{ fontSize: 12, fontFamily: FONTS.mono, color: DARK_THEME.textMuted }}>{right}</span>
    </div>
  );

  const roleBars = (
    capacity: Record<string, number>,
    demand: Record<string, number>,
    employees: ResourceEmployee[],
  ) => (
    <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      {CORE_ROLE_KEYS.map((r) => (
        <RoleCapacityBar
          key={r}
          role={r}
          demand={demand[r] ?? 0}
          capacity={capacity[r] ?? 0}
          employeeCount={employees.filter((e) => e.role === r).length}
        />
      ))}
      {infoRoles.map((r) => (
        <RoleCapacityBar
          key={r.code}
          role={r.code}
          demand={demand[r.code] ?? 0}
          capacity={capacity[r.code] ?? 0}
          employeeCount={employees.filter((e) => e.role === r.code).length}
        />
      ))}
    </div>
  );

  const toggleIn = (
    set: React.Dispatch<React.SetStateAction<Set<string>>>,
    id: string,
  ) =>
    set((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const sortedEmployees = (list: ResourceEmployee[]) =>
    [...list].sort((a, b) => {
      const d = roleSortKey(a.role) - roleSortKey(b.role);
      return d !== 0 ? d : a.display_name.localeCompare(b.display_name, 'ru');
    });

  const renderEmployee = (e: ResourceEmployee) => {
            const knownRole = e.role && roles.some(r => r.code === e.role && r.is_active) ? e.role : null;
            const roleColor = knownRole ? getRoleColor(roles, knownRole) : DARK_THEME.textDim;
            const roleShort = knownRole ? getRoleShort(knownRole) : '—';
            const mandPct = knownRole ? (mandatoryPctByRole[knownRole] ?? 0) : 0;

            // Норма-часы (до вычета обяз. работ). Если mandPct=0 — норма равна total_hours.
            const normHours = mandPct > 0 && e.total_hours > 0
              ? Math.round(e.total_hours / (1 - mandPct / 100))
              : Math.round(e.total_hours);

            return (
              <div key={e.employee_id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        width: 26, height: 18, borderRadius: 3,
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        background: roleColor, color: '#00202a',
                        fontSize: 11, fontWeight: 700, fontFamily: FONTS.mono,
                      }}
                    >
                      {roleShort}
                    </span>
                    <span style={{ color: knownRole ? DARK_THEME.textPrimary : DARK_THEME.textMuted, fontSize: 15 }}>
                      {e.display_name}
                    </span>
                    {!!e.shared_with?.length && (
                      <Tooltip
                        title={`Делит время с командами: ${e.shared_with.join(', ')}. `
                          + `Заложено всеми командами: ${Math.round(e.committed_hours_all_teams ?? 0)} ч`
                          + (e.is_overcommitted ? ' — больше его нормы' : '')}
                      >
                        <Tag color={e.is_overcommitted ? 'red' : 'blue'}>общий</Tag>
                      </Tooltip>
                    )}
                    {!knownRole && (
                      <Select
                        size="small"
                        placeholder="роль"
                        style={{ width: 110, fontSize: 11 }}
                        options={roles.filter((r) => r.is_active).map((r) => ({ label: r.label, value: r.code }))}
                        loading={setRoleMutation.isPending}
                        onChange={(value: string) =>
                          setRoleMutation.mutate({ employeeId: e.employee_id, role: value })
                        }
                        onClick={(ev) => ev.stopPropagation()}
                      />
                    )}
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: 14, color: DARK_THEME.textMuted, fontFamily: FONTS.mono }}>
                      {Math.round(e.total_hours)} ч
                    </span>
                    <div style={{ fontSize: 12, color: DARK_THEME.textHint }}>
                      норма {normHours} ч{mandPct > 0 ? ` · −${mandPct}%` : ''}
                    </div>
                  </div>
                </div>
                {/* Demand / capacity bar */}
                {(() => {
                  const empDemand = demandByEmployee[e.employee_id] ?? 0;
                  const empCapacity = e.total_hours;
                  const pct = empCapacity > 0 ? Math.min((empDemand / empCapacity) * 100, 100) : 0;
                  const over = empDemand > empCapacity && empCapacity > 0;
                  return (
                    <>
                      <div style={{ position: 'relative', height: 5, background: DARK_THEME.darkAccent, borderRadius: 2, overflow: 'hidden', marginTop: 4 }}>
                        <div style={{ position: 'absolute', inset: 0, transform: `scaleX(${pct / 100})`, transformOrigin: 'left', background: over ? DARK_THEME.amber : roleColor, transition: 'transform 0.2s' }} />
                      </div>
                      {empDemand > 0 && (
                        <div style={{ fontSize: 12, color: over ? DARK_THEME.amber : DARK_THEME.textDim, marginTop: 1, textAlign: 'right', fontFamily: FONTS.mono }}>
                          {Math.round(empDemand)} / {Math.round(empCapacity)} ч
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 1. Overall gauge */}
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
          <span style={{ fontSize: 14, color: DARK_THEME.textMuted, textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Ресурс команды · Q{quarter}
          </span>
          {resourceBase.external_qa_hours != null && (
            <Tag color="purple" style={{ fontSize: 12, lineHeight: '20px' }}>
              внешний QA {Math.round(resourceBase.external_qa_hours)} ч
            </Tag>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 44, fontWeight: 700, color: overallOver ? DARK_THEME.amber : DARK_THEME.textPrimary, fontFamily: FONTS.mono, lineHeight: 1 }}>
            {Math.round(totalDemand)}
          </span>
          <span style={{ fontSize: 18, color: DARK_THEME.textMuted }}>/</span>
          <span style={{ fontSize: 26, color: DARK_THEME.textMuted, fontFamily: FONTS.mono }}>
            {Math.round(totalCapacity)} ч
          </span>
        </div>
        <div style={{ fontSize: 14, color: DARK_THEME.textHint, marginBottom: 10 }}>
          {overallOver
            ? 'Перегруз по одной или нескольким ролям — см. ниже'
            : totalCapacity > 0
              ? `Запас ${freeHours} ч · ${freePct}% свободно · включено ${includedCount} идей`
              : 'Нет данных о ёмкости'}
        </div>
        <div style={{ position: 'relative', height: 14, background: DARK_THEME.darkAccent, borderRadius: 7, overflow: 'hidden' }}>
          <div
            style={{
              position: 'absolute', left: 0, right: 0, top: 0, bottom: 0,
              transform: `scaleX(${plannedPct / 100})`,
              transformOrigin: 'left',
              background: overallOver ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
              transition: 'transform .2s',
            }}
          />
        </div>
      </Card>

      {/* 2. Per-role */}
      <Card
        title="Ресурс по ролям"
        styles={{ body: { padding: 0 } }}
        extra={<span style={{ fontSize: 13, color: DARK_THEME.textMuted }}>план / доступно</span>}
      >
        {hasSubgroups ? (
          groupSections.map((sec) => {
            const collapsed = collapsedRoleGroups.has(sec.id);
            const capacity = summary?.available_by_subgroup_role?.[sec.id] ?? {};
            const demand = demandBySubgroupRole[sec.id] ?? {};
            const capTotal = Object.values(capacity).reduce((acc, v) => acc + v, 0);
            const demTotal = Object.values(demand).reduce((acc, v) => acc + v, 0);
            return (
              <div key={sec.id || '__none__'}>
                {sectionHeader(
                  sec.name,
                  `${Math.round(demTotal)} / ${Math.round(capTotal)} ч`,
                  collapsed,
                  () => toggleIn(setCollapsedRoleGroups, sec.id),
                )}
                {!collapsed && roleBars(capacity, demand, sec.employees)}
              </div>
            );
          })
        ) : (
          roleBars(availableByRole, demandByEmployeeRole, resourceBase.employees)
        )}
      </Card>

      {/* 3. По сотрудникам */}
      <Card title="По сотрудникам" styles={{ body: { padding: 0 } }}>
        <div
          style={{
            // При секциях внешний отступ снимаем: заголовки групп идут во всю ширину.
            padding: hasSubgroups ? 0 : '8px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: hasSubgroups ? 0 : 9,
          }}
        >
          {hasSubgroups
            ? groupSections.map((sec) => {
                const collapsed = collapsedEmpGroups.has(sec.id);
                return (
                  <div key={sec.id || '__none__'}>
                    {sectionHeader(
                      sec.name,
                      `${sec.employees.length} чел.`,
                      collapsed,
                      () => toggleIn(setCollapsedEmpGroups, sec.id),
                    )}
                    {!collapsed && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 9, padding: '8px 14px' }}>
                        {sortedEmployees(sec.employees).map(renderEmployee)}
                      </div>
                    )}
                  </div>
                );
              })
            : sortedEmployees(resourceBase.employees).map(renderEmployee)}
          {resourceBase.employees.length === 0 && (
            <div style={{ color: DARK_THEME.textMuted, fontSize: 12, padding: 8 }}>
              Нет сотрудников в команде.
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

const PlanningCapacityPanel = memo(PlanningCapacityPanelBase);
export default PlanningCapacityPanel;
