import React, { useMemo } from 'react';
import { Card, Collapse, Select, Skeleton, Tag } from 'antd';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { DARK_THEME, FONTS } from '../../utils/constants';
import { useRoles } from '../../hooks/useRoles';
import { getRoleColor } from '../../utils/roles';
import type { AllocationResponse, ResourceBase, ResourceSummaryOut } from '../../types/api';
import { demandByRole } from '../../utils/planning';
import RoleCapacityBar from './RoleCapacityBar';
import { patchEmployee } from '../../api/employees';

const CORE_ROLE_KEYS = ['analyst', 'dev', 'qa'] as const;
type CoreRoleKey = (typeof CORE_ROLE_KEYS)[number];

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

function getRoleShort(role: string): string {
  return ROLE_SHORT_LOCAL[role] ?? role.slice(0, 2).toUpperCase();
}

/** Детализация ресурса по ролям: брутто → отпуска → обяз. работы → доступно */
function ResourceBreakdownTable({ summary }: { summary: ResourceSummaryOut }) {
  const roles = summary.roles;

  const vacationByRole: Record<string, number> = {};
  for (const role of roles) {
    const cal = summary.calendar_gross_by_role[role] ?? 0;
    const gross = summary.total_by_role[role] ?? 0;
    vacationByRole[role] = Math.round(cal - gross);
  }

  const calTotal = Math.round(Object.values(summary.calendar_gross_by_role).reduce((s, v) => s + v, 0));
  const vacTotal = Math.round(Object.values(vacationByRole).reduce((s, v) => s + v, 0));
  const availTotal = Math.round(summary.available_for_backlog_total);

  const cellStyle: React.CSSProperties = {
    padding: '4px 8px',
    textAlign: 'right',
    fontFamily: FONTS.mono,
    fontSize: 12,
    color: DARK_THEME.textSecondary,
  };
  const labelStyle: React.CSSProperties = {
    padding: '4px 8px',
    fontSize: 11,
    color: DARK_THEME.textMuted,
  };
  const tableStyle: React.CSSProperties = {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: 12,
  };

  // Строки обязательных работ, которые вычитаются из пула
  const subtractingRows = summary.work_type_rows.filter((r) => r.subtracts_from_pool);
  // Строки информационных работ (не вычитаются)
  const infoRows = summary.work_type_rows.filter((r) => !r.subtracts_from_pool);

  const mandatoryByRole: Record<string, number> = {};
  for (const role of roles) mandatoryByRole[role] = 0;
  for (const row of subtractingRows) {
    for (const role of roles) {
      mandatoryByRole[role] = (mandatoryByRole[role] ?? 0) + Math.round(row.by_role[role] ?? 0);
    }
  }
  const mandTotal = Math.round(Object.values(mandatoryByRole).reduce((s, v) => s + v, 0));

  return (
    <div style={{ marginTop: 4 }}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={{ ...labelStyle, textAlign: 'left' }} />
            {roles.map((r) => (
              <th key={r} style={{ ...cellStyle, fontSize: 10, color: DARK_THEME.textHint }}>
                {getRoleShort(r)}
              </th>
            ))}
            <th style={{ ...cellStyle, fontSize: 10, color: DARK_THEME.textHint }}>Итого</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style={labelStyle}>Брутто</td>
            {roles.map((r) => (
              <td key={r} style={cellStyle}>{Math.round(summary.calendar_gross_by_role[r] ?? 0)}</td>
            ))}
            <td style={{ ...cellStyle, fontWeight: 600, color: DARK_THEME.textPrimary }}>{calTotal}</td>
          </tr>
          <tr>
            <td style={{ ...labelStyle, color: DARK_THEME.textHint }}>− Отпуска</td>
            {roles.map((r) => (
              <td key={r} style={{ ...cellStyle, color: DARK_THEME.textHint }}>
                {vacationByRole[r] > 0 ? `−${vacationByRole[r]}` : '—'}
              </td>
            ))}
            <td style={{ ...cellStyle, color: DARK_THEME.textHint }}>{vacTotal > 0 ? `−${vacTotal}` : '—'}</td>
          </tr>

          {/* Каждый вид обязательных работ отдельной строкой */}
          {subtractingRows.map((row) => (
            <tr key={row.work_type_id}>
              <td style={{ ...labelStyle, color: DARK_THEME.textHint, paddingLeft: 16 }}>
                − {row.work_type_label}
              </td>
              {roles.map((r) => {
                const h = Math.round(row.by_role[r] ?? 0);
                return (
                  <td key={r} style={{ ...cellStyle, color: DARK_THEME.textHint }}>
                    {h > 0 ? `−${h}` : '—'}
                  </td>
                );
              })}
              <td style={{ ...cellStyle, color: DARK_THEME.textHint }}>
                {Math.round(row.total) > 0 ? `−${Math.round(row.total)}` : '—'}
              </td>
            </tr>
          ))}

          {subtractingRows.length === 0 && (
            <tr>
              <td style={{ ...labelStyle, color: DARK_THEME.textHint }}>− Обяз. работы</td>
              {roles.map((r) => (
                <td key={r} style={{ ...cellStyle, color: DARK_THEME.textHint }}>
                  {mandatoryByRole[r] > 0 ? `−${mandatoryByRole[r]}` : '—'}
                </td>
              ))}
              <td style={{ ...cellStyle, color: DARK_THEME.textHint }}>{mandTotal > 0 ? `−${mandTotal}` : '—'}</td>
            </tr>
          )}

          <tr style={{ borderTop: `1px solid ${DARK_THEME.border}` }}>
            <td style={{ ...labelStyle, color: DARK_THEME.cyanPrimary, fontWeight: 600 }}>= Доступно</td>
            {roles.map((r) => (
              <td key={r} style={{ ...cellStyle, color: DARK_THEME.cyanPrimary, fontWeight: 600 }}>
                {Math.round(summary.available_for_backlog_by_role[r] ?? 0)}
              </td>
            ))}
            <td style={{ ...cellStyle, color: DARK_THEME.cyanPrimary, fontWeight: 700 }}>{availTotal}</td>
          </tr>
          <tr>
            <td style={{ ...labelStyle, fontSize: 10 }} />
            {roles.map((r) => (
              <td key={r} style={{ ...cellStyle, fontSize: 10, color: DARK_THEME.textHint }}>
                {(summary.role_employee_names[r] ?? []).length} чел.
              </td>
            ))}
            <td />
          </tr>

          {/* Информационные работы (не вычитаются) */}
          {infoRows.length > 0 && (
            <tr>
              <td
                colSpan={roles.length + 2}
                style={{ ...labelStyle, fontSize: 10, color: DARK_THEME.textHint, paddingTop: 8, borderTop: `1px solid ${DARK_THEME.border}` }}
              >
                Справочно (не вычитаются из пула)
              </td>
            </tr>
          )}
          {infoRows.map((row) => (
            <tr key={row.work_type_id}>
              <td style={{ ...labelStyle, color: DARK_THEME.textHint, paddingLeft: 16, fontSize: 10 }}>
                {row.work_type_label}
              </td>
              {roles.map((r) => {
                const h = Math.round(row.by_role[r] ?? 0);
                return (
                  <td key={r} style={{ ...cellStyle, color: DARK_THEME.textHint, fontSize: 10 }}>
                    {h > 0 ? h : '—'}
                  </td>
                );
              })}
              <td style={{ ...cellStyle, color: DARK_THEME.textHint, fontSize: 10 }}>
                {Math.round(row.total) > 0 ? Math.round(row.total) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {summary.absence_days_by_employee.length > 0 && (
        <div style={{ marginTop: 10, borderTop: `1px solid ${DARK_THEME.border}`, paddingTop: 8 }}>
          <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Отпуска по сотрудникам
          </div>
          {summary.absence_days_by_employee.map((emp) => (
            <div key={emp.employee_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: DARK_THEME.textMuted, marginBottom: 3 }}>
              <span>{emp.display_name}</span>
              <span style={{ fontFamily: FONTS.mono }}>
                {emp.role ? getRoleShort(emp.role) : '—'} · {emp.days} дн
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PlanningCapacityPanel({ resourceBase, summary, allocations, quarter, scenarioId }: Props) {
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

  const demand = useMemo(() => demandByRole(allocations), [allocations]);

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

  const capacityByRole: Record<CoreRoleKey, number> = {
    analyst: availableByRole['analyst'] ?? 0,
    dev:     availableByRole['dev']     ?? 0,
    qa: resourceBase.external_qa_hours != null
      ? resourceBase.external_qa_hours
      : (availableByRole['qa'] ?? 0),
  };

  const infoRoles = roles.filter(
    (r) => r.counts_in_planning && !(CORE_ROLE_KEYS as readonly string[]).includes(r.code),
  );

  const totalCapacity = Object.values(capacityByRole).reduce((s, v) => s + v, 0)
    + infoRoles.reduce((s, r) => s + (availableByRole[r.code] ?? 0), 0);
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, position: 'sticky', top: 16 }}>
      {/* 1. Overall gauge */}
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
          <span style={{ fontSize: 11, color: DARK_THEME.textMuted, textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Ресурс команды · Q{quarter}
          </span>
          {resourceBase.external_qa_hours != null && (
            <Tag color="purple" style={{ fontSize: 10, lineHeight: '18px' }}>
              внешний QA {Math.round(resourceBase.external_qa_hours)} ч
            </Tag>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 42, fontWeight: 700, color: overallOver ? DARK_THEME.amber : DARK_THEME.textPrimary, fontFamily: FONTS.mono, lineHeight: 1 }}>
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
        <div style={{ position: 'relative', height: 14, background: DARK_THEME.darkAccent, borderRadius: 7, overflow: 'hidden' }}>
          <div
            style={{
              position: 'absolute', left: 0, top: 0, bottom: 0,
              width: `${plannedPct}%`,
              background: overallOver ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
              transition: 'width .2s',
            }}
          />
        </div>
        {summary && (
          <Collapse
            ghost
            style={{ marginTop: 8 }}
            items={[{
              key: 'breakdown',
              label: <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>Разбивка по ролям ↓</span>,
              children: <ResourceBreakdownTable summary={summary} />,
            }]}
          />
        )}
      </Card>

      {/* 2. Per-role */}
      <Card
        title="Ресурс по ролям"
        styles={{ body: { padding: 0 } }}
        extra={<span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>план / доступно</span>}
      >
        <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {CORE_ROLE_KEYS.map((r) => (
            <div key={r}>
              <RoleCapacityBar
                role={r}
                demand={demand[r] ?? 0}
                capacity={capacityByRole[r]}
                employeeCount={resourceBase.employees.filter((e) => e.role === r).length}
              />
              {summary && mandatoryPctByRole[r] != null && mandatoryPctByRole[r] > 0 && (
                <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 2, paddingLeft: 2 }}>
                  обяз. работы {mandatoryPctByRole[r]}% · норма {Math.round((summary.total_by_role[r] ?? 0))} ч
                </div>
              )}
            </div>
          ))}
          {infoRoles.map((r) => (
            <div key={r.code}>
              <RoleCapacityBar
                role={r.code}
                demand={0}
                capacity={availableByRole[r.code] ?? 0}
                employeeCount={resourceBase.employees.filter((e) => e.role === r.code).length}
              />
              {summary && mandatoryPctByRole[r.code] != null && mandatoryPctByRole[r.code] > 0 && (
                <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 2, paddingLeft: 2 }}>
                  обяз. работы {mandatoryPctByRole[r.code]}% · норма {Math.round((summary.total_by_role[r.code] ?? 0))} ч
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* 3. По сотрудникам */}
      <Card title="По сотрудникам" styles={{ body: { padding: 0 } }}>
        <div style={{ padding: '8px 14px', display: 'flex', flexDirection: 'column', gap: 9 }}>
          {resourceBase.employees.map((e) => {
            const knownRole = e.role && roles.some(r => r.code === e.role && r.is_active) ? e.role : null;
            const roleColor = knownRole ? getRoleColor(roles, knownRole) : DARK_THEME.textDim;
            const roleShort = knownRole ? getRoleShort(knownRole) : '—';
            const mandPct = knownRole ? (mandatoryPctByRole[knownRole] ?? 0) : 0;

            // Норма-часы (до вычета обяз. работ) — пересчитываем из total_hours и mandPct
            const normHours = mandPct > 0 && e.total_hours > 0
              ? Math.round(e.total_hours / (1 - mandPct / 100))
              : null;

            return (
              <div key={e.employee_id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        width: 22, height: 16, borderRadius: 3,
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        background: roleColor, color: '#00202a',
                        fontSize: 9, fontWeight: 700, fontFamily: FONTS.mono,
                      }}
                    >
                      {roleShort}
                    </span>
                    <span style={{ color: knownRole ? DARK_THEME.textPrimary : DARK_THEME.textMuted, fontSize: 13 }}>
                      {e.display_name}
                    </span>
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
                    <span style={{ fontSize: 12, color: DARK_THEME.textMuted, fontFamily: FONTS.mono }}>
                      {Math.round(e.total_hours)} ч
                    </span>
                    {normHours != null && (
                      <div style={{ fontSize: 10, color: DARK_THEME.textHint }}>
                        норма {normHours} ч · −{mandPct}%
                      </div>
                    )}
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
                      <div style={{ display: 'flex', height: 5, background: DARK_THEME.darkAccent, borderRadius: 2, overflow: 'hidden', marginTop: 4 }}>
                        <div style={{ width: `${pct}%`, background: over ? DARK_THEME.amber : roleColor, transition: 'width 0.2s' }} />
                      </div>
                      {empDemand > 0 && (
                        <div style={{ fontSize: 10, color: over ? DARK_THEME.amber : DARK_THEME.textDim, marginTop: 1, textAlign: 'right', fontFamily: FONTS.mono }}>
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
