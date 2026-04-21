import { useMemo } from 'react';
import { Card, Select, Skeleton, Tag } from 'antd';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { DARK_THEME, FONTS } from '../../utils/constants';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel, getRoleColor } from '../../utils/roles';
import type { AllocationResponse, ResourceBase, ResourceSummaryOut } from '../../types/api';
import { demandByRole } from '../../utils/planning';
import RoleCapacityBar from './RoleCapacityBar';
import { patchEmployee } from '../../api/employees';

// Core planning roles contributing to backlog demand (analyst/dev/qa).
// Informational roles (e.g. consultant — capacity only, no demand) pulled
// дополнительно ниже из реестра по флагу counts_in_planning.
const CORE_ROLE_KEYS = ['analyst', 'dev', 'qa'] as const;
type CoreRoleKey = (typeof CORE_ROLE_KEYS)[number];

// Short abbreviations for role badges in the employee list
const ROLE_SHORT_LOCAL: Record<string, string> = {
  analyst: 'АН',
  dev: 'ПР',
  qa: 'ТС',
  consultant: 'КН',
  project_manager: 'РП',
  other: 'ДР',
};

interface Props {
  resourceBase: ResourceBase | undefined;
  allocations: AllocationResponse[];
  quarter: string;
  scenarioId: string;
  summary?: ResourceSummaryOut;
}

/** Правая sticky-колонка /planning: карточки с ресурсом по ролям и сотрудникам.
 *  Ёмкость берётся из resourceBase (Task 24, /scenarios/:id/resource).
 *  Потребность считается на клиенте через demandByRole — мгновенно при клике. */
export default function PlanningCapacityPanel({ resourceBase, allocations, quarter, scenarioId }: Props) {
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

  // Пересчёт потребности по ролям при каждом изменении раскладок — O(n), <1ms
  const demand = useMemo(() => demandByRole(allocations), [allocations]);

  // Потребность по конкретным сотрудникам — часы из included-раскладок
  const demandByEmployee = useMemo(() => {
    const result: Record<string, number> = {};
    for (const alloc of allocations) {
      if (!alloc.included || !alloc.assignee_employee_id) continue;
      const emp = resourceBase?.employees.find(
        (e) => e.employee_id === alloc.assignee_employee_id,
      );
      if (!emp?.role) continue;
      const hours =
        emp.role === 'analyst'
          ? (alloc.estimate_analyst_hours ?? 0)
          : emp.role === 'dev'
            ? (alloc.estimate_dev_hours ?? 0)
            : emp.role === 'qa'
              ? (alloc.estimate_qa_hours ?? 0)
              : emp.role === 'consultant'
                ? (alloc.estimate_opo_hours ?? 0)
                : 0;
      result[alloc.assignee_employee_id] = (result[alloc.assignee_employee_id] ?? 0) + hours;
    }
    return result;
  }, [allocations, resourceBase]);

  if (!resourceBase) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, position: 'sticky', top: 16 }}>
        <Card>
          <Skeleton active paragraph={{ rows: 3 }} />
        </Card>
        <Card>
          <Skeleton active paragraph={{ rows: 4 }} />
        </Card>
        <Card>
          <Skeleton active paragraph={{ rows: 5 }} />
        </Card>
      </div>
    );
  }

  const capacityByRole: Record<CoreRoleKey, number> = {
    analyst: resourceBase.role_totals['analyst'] ?? 0,
    dev:     resourceBase.role_totals['dev'] ?? 0,
    // Если задан внешний QA-резерв — используем его, иначе берём из role_totals
    qa: resourceBase.external_qa_hours != null
      ? resourceBase.external_qa_hours
      : (resourceBase.role_totals['qa'] ?? 0),
  };

  // Дополнительные роли из реестра: counts_in_planning=true, но не из core —
  // отображаются информационно (capacity без demand; запас = capacity).
  const infoRoles = roles.filter(
    (r) => r.counts_in_planning && !(CORE_ROLE_KEYS as readonly string[]).includes(r.code),
  );

  const totalCapacity = CORE_ROLE_KEYS.reduce((s, r) => s + capacityByRole[r], 0);
  const totalDemand = CORE_ROLE_KEYS.reduce((s, r) => s + (demand[r] ?? 0), 0);
  const overallOver = CORE_ROLE_KEYS.some(
    (r) => (demand[r] ?? 0) > capacityByRole[r] && capacityByRole[r] > 0,
  );
  const freeHours = Math.max(0, Math.round(totalCapacity - totalDemand));
  const freePct = totalCapacity > 0
    ? Math.max(0, Math.round((1 - totalDemand / totalCapacity) * 100))
    : 0;
  const plannedPct = totalCapacity > 0
    ? Math.min(100, (totalDemand / totalCapacity) * 100)
    : 0;

  const includedCount = allocations.filter((a) => a.included).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, position: 'sticky', top: 16 }}>
      {/* 1. Overall gauge */}
      <Card>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            marginBottom: 10,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: DARK_THEME.textMuted,
              textTransform: 'uppercase',
              letterSpacing: 0.8,
            }}
          >
            Ресурс команды · Q{quarter}
          </span>
          {resourceBase.external_qa_hours != null && (
            <Tag color="purple" style={{ fontSize: 10, lineHeight: '18px' }}>
              внешний QA {Math.round(resourceBase.external_qa_hours)} ч
            </Tag>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
          <span
            style={{
              fontSize: 42,
              fontWeight: 700,
              color: overallOver ? DARK_THEME.amber : DARK_THEME.textPrimary,
              fontFamily: FONTS.mono,
              lineHeight: 1,
            }}
          >
            {Math.round(totalDemand)}
          </span>
          <span style={{ fontSize: 16, color: DARK_THEME.textMuted }}>/</span>
          <span style={{ fontSize: 24, color: DARK_THEME.textMuted, fontFamily: FONTS.mono }}>
            {Math.round(totalCapacity)} ч
          </span>
        </div>
        <div style={{ fontSize: 11, color: DARK_THEME.textHint, marginBottom: 10 }}>
          {overallOver
            ? 'Перегруз по одной или нескольким ролям — см. ниже'
            : totalCapacity > 0
              ? `Запас ${freeHours} ч · ${freePct}% свободно · включено ${includedCount} идей`
              : 'Нет данных о ёмкости'}
        </div>
        <div
          style={{
            position: 'relative',
            height: 14,
            background: DARK_THEME.darkAccent,
            borderRadius: 7,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              bottom: 0,
              width: `${plannedPct}%`,
              background: overallOver ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
              transition: 'width .2s',
            }}
          />
        </div>
      </Card>

      {/* 2. Per-role */}
      <Card
        title="Ресурс по ролям"
        styles={{ body: { padding: 0 } }}
        extra={<span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>план / доступно</span>}
      >
        <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {CORE_ROLE_KEYS.map((r) => (
            <RoleCapacityBar
              key={r}
              role={r}
              demand={demand[r] ?? 0}
              capacity={capacityByRole[r]}
              employeeCount={resourceBase.employees.filter((e) => e.role === r).length}
            />
          ))}
          {infoRoles.map((r) => (
            <RoleCapacityBar
              key={r.code}
              role={r.code}
              demand={0}
              capacity={resourceBase.role_totals[r.code] ?? 0}
              employeeCount={resourceBase.employees.filter((e) => e.role === r.code).length}
            />
          ))}
        </div>
      </Card>

      {/* 3. По сотрудникам */}
      <Card title="По сотрудникам" styles={{ body: { padding: 0 } }}>
        <div style={{ padding: '8px 14px', display: 'flex', flexDirection: 'column', gap: 9 }}>
          {resourceBase.employees.map((e) => {
            const knownRole = e.role && roles.some(r => r.code === e.role && r.is_active) ? e.role : null;
            const roleColor = knownRole ? getRoleColor(roles, knownRole) : DARK_THEME.textDim;
            const roleShort = knownRole
              ? (ROLE_SHORT_LOCAL[knownRole] ?? knownRole.slice(0, 2).toUpperCase())
              : '—';
            return (
              <div key={e.employee_id}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        width: 22,
                        height: 16,
                        borderRadius: 3,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: roleColor,
                        color: '#00202a',
                        fontSize: 9,
                        fontWeight: 700,
                        fontFamily: FONTS.mono,
                      }}
                    >
                      {roleShort}
                    </span>
                    <span
                      style={{
                        color: knownRole ? DARK_THEME.textPrimary : DARK_THEME.textMuted,
                        fontSize: 13,
                      }}
                    >
                      {e.display_name}
                    </span>
                    {!knownRole && (
                      <Select
                        size="small"
                        placeholder="роль"
                        style={{ width: 110, fontSize: 11 }}
                        options={roles
                          .filter((r) => r.is_active)
                          .map((r) => ({ label: r.label, value: r.code }))}
                        loading={setRoleMutation.isPending}
                        onChange={(value: string) =>
                          setRoleMutation.mutate({ employeeId: e.employee_id, role: value })
                        }
                        onClick={(ev) => ev.stopPropagation()}
                      />
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: 12,
                      color: DARK_THEME.textMuted,
                      fontFamily: FONTS.mono,
                    }}
                  >
                    {Math.round(e.total_hours)} ч
                  </span>
                </div>
                {/* Demand / capacity bar */}
                {(() => {
                  const empDemand = demandByEmployee[e.employee_id] ?? 0;
                  const empCapacity = e.total_hours;
                  const pct = empCapacity > 0 ? Math.min((empDemand / empCapacity) * 100, 100) : 0;
                  const over = empDemand > empCapacity && empCapacity > 0;
                  return (
                    <>
                      <div
                        style={{
                          display: 'flex',
                          height: 5,
                          background: DARK_THEME.darkAccent,
                          borderRadius: 2,
                          overflow: 'hidden',
                          marginTop: 4,
                        }}
                      >
                        <div
                          style={{
                            width: `${pct}%`,
                            background: over ? DARK_THEME.amber : roleColor,
                            transition: 'width 0.2s',
                          }}
                        />
                      </div>
                      {empDemand > 0 && (
                        <div
                          style={{
                            fontSize: 10,
                            color: over ? DARK_THEME.amber : DARK_THEME.textDim,
                            marginTop: 1,
                            textAlign: 'right',
                            fontFamily: FONTS.mono,
                          }}
                        >
                          {Math.round(empDemand)} / {Math.round(empCapacity)} ч
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            );
          })}
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
