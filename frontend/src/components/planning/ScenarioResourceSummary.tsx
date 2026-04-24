import React, { useMemo, useState } from 'react';
import { Card, Skeleton, Tooltip } from 'antd';
import { useScenarioResourceSummary } from '../../hooks/usePlanning';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel, getRoleColor } from '../../utils/roles';
import { DARK_THEME, FONTS } from '../../utils/constants';
import { demandByAssigneeRole, demandByRole } from '../../utils/planning';
import type { AllocationResponse, ResourceEmployee } from '../../types/api';

interface Props {
  scenarioId: string;
  enabled: boolean;
  allocations?: AllocationResponse[];
  employees?: ResourceEmployee[];
}

const CELL: React.CSSProperties = {
  padding: '7px 10px',
  textAlign: 'right' as const,
  fontFamily: FONTS.mono,
  fontSize: 14,
};

const CELL_LABEL: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 13,
  color: DARK_THEME.textMuted,
};

const ROW_DIVIDER = `1px solid rgba(255,255,255,0.06)`;

export default function ScenarioResourceSummary({ scenarioId, enabled, allocations, employees }: Props) {
  const { data: summary, isLoading } = useScenarioResourceSummary(scenarioId, enabled);
  const { data: roles = [] } = useRoles();

  const LS_KEY = 'planning_resource_table_collapsed';
  const [collapsed, setCollapsed] = useState<boolean>(() => localStorage.getItem(LS_KEY) === 'true');

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(LS_KEY, String(next));
      return next;
    });
  };

  // Потребность по роли исполнителя: часы РП идут в пул РП, не аналитика
  const roleDemand = useMemo(() => {
    if (!allocations) return { analyst: 0, dev: 0, qa: 0 };
    return employees && employees.length > 0
      ? demandByAssigneeRole(allocations, employees)
      : demandByRole(allocations);
  }, [allocations, employees]);

  if (isLoading) {
    return (
      <Card styles={{ body: { padding: 14 } }}>
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (!summary || summary.roles.length === 0) return null;

  if (collapsed) {
    const collapsedTotalDemand = Object.values(roleDemand).reduce((s, v) => s + v, 0);
    const collapsedTotalRemaining = Math.round(summary.available_for_backlog_total - collapsedTotalDemand);
    const collapsedTotalDeficit = collapsedTotalRemaining < 0;
    return (
      <Card styles={{ body: { padding: 0, overflow: 'hidden' } }}>
        <div style={{ display: 'flex', alignItems: 'center', height: 40 }}>
          <div style={{
            padding: '0 14px',
            fontSize: 12,
            color: DARK_THEME.textMuted,
            borderRight: `1px solid ${DARK_THEME.border}`,
            background: DARK_THEME.darkAccent,
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            whiteSpace: 'nowrap' as const,
          }}>
            На бэклог
          </div>
          {summary.roles.map((role) => {
            const avail = summary.available_for_backlog_by_role[role] ?? 0;
            const used = roleDemand[role as keyof typeof roleDemand] ?? 0;
            const remaining = Math.round(avail - used);
            const isDeficit = remaining < 0;
            const hasUsed = used > 0;
            return (
              <div key={role} style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '0 16px',
                borderRight: `1px solid ${DARK_THEME.border}`,
                height: '100%',
              }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: getRoleColor(roles, role) }}>
                  {getRoleLabel(roles, role)}
                </span>
                <span style={{ fontSize: 14, fontWeight: 700, fontFamily: FONTS.mono, color: isDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary }}>
                  {hasUsed ? remaining : Math.round(avail)} ч
                </span>
              </div>
            );
          })}
          <div style={{
            padding: '0 16px',
            borderRight: `1px solid ${DARK_THEME.border}`,
            height: '100%',
            display: 'flex',
            alignItems: 'center',
          }}>
            <span style={{ fontSize: 15, fontWeight: 700, fontFamily: FONTS.mono, color: collapsedTotalDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary }}>
              {collapsedTotalDemand > 0 ? collapsedTotalRemaining : Math.round(summary.available_for_backlog_total)} ч
            </span>
          </div>
          <button
            onClick={toggleCollapsed}
            style={{
              marginLeft: 'auto',
              padding: '0 14px',
              height: '100%',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 11,
              color: DARK_THEME.textMuted,
            }}
          >
            ↓ Развернуть
          </button>
        </div>
      </Card>
    );
  }

  const gridCols = `minmax(280px, max-content) repeat(${summary.roles.length}, 1fr) minmax(100px, max-content)`;

  const roleBorderStyle = (role: string): React.CSSProperties => {
    const color = getRoleColor(roles, role);
    const isLast = role === summary.roles[summary.roles.length - 1];
    return {
      borderLeft: `2px solid ${color}`,
      ...(isLast ? { borderRight: `2px solid ${color}` } : {}),
    };
  };

  const roleCellStyle = (role: string): React.CSSProperties => {
    const color = getRoleColor(roles, role);
    const isLast = role === summary.roles[summary.roles.length - 1];
    return {
      borderLeft: `2px solid ${color}`,
      ...(isLast ? { borderRight: `2px solid ${color}` } : {}),
      background: `${color}08`,
    };
  };

  const headerStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: gridCols,
    gap: 1,
    background: DARK_THEME.border,
    borderRadius: '6px 6px 0 0',
    overflow: 'hidden',
  };

  const rowStyle = (opts?: { borderTop?: string }): React.CSSProperties => ({
    display: 'grid',
    gridTemplateColumns: gridCols,
    gap: 1,
    background: DARK_THEME.border,
    borderTop: opts?.borderTop ?? ROW_DIVIDER,
  });

  const totalDemand = Object.values(roleDemand).reduce((s, v) => s + v, 0);

  return (
    <Card styles={{ body: { padding: 0, overflow: 'hidden', borderRadius: 8 } }}>
      <div style={{ display: 'flex', alignItems: 'stretch' }}>
        {/* Основная таблица */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Кнопка свернуть — всегда над таблицей */}
          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            padding: '4px 10px',
            borderBottom: `1px solid ${DARK_THEME.border}`,
            background: DARK_THEME.cardBg,
          }}>
            <button
              onClick={toggleCollapsed}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: 11,
                color: DARK_THEME.textMuted,
                padding: '2px 4px',
              }}
            >
              ↑ Свернуть
            </button>
          </div>
          {/* Header row */}
          <div style={headerStyle}>
            <div style={{ ...CELL_LABEL, background: DARK_THEME.darkAccent }} />
            {summary.roles.map((role) => {
              const names = summary.role_employee_names[role] ?? [];
              const label = getRoleLabel(roles, role);
              return (
                <Tooltip
                  key={role}
                  title={
                    names.length > 0 ? (
                      <div>{names.map((n) => <div key={n}>{n}</div>)}</div>
                    ) : 'Нет сотрудников'
                  }
                >
                  <div
                    style={{
                      ...CELL,
                      ...roleCellStyle(role),
                      textAlign: 'center',
                      color: DARK_THEME.textSecondary,
                      cursor: 'default',
                      paddingTop: 10,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 6 }}>
                      <span style={{ fontWeight: 600, color: getRoleColor(roles, role) }}>{label}</span>
                      <span style={{ fontSize: 11, color: DARK_THEME.textHint }}>
                        · {names.length} чел. ⓘ
                      </span>
                    </div>
                    <div
                      style={{
                        height: 3,
                        background: getRoleColor(roles, role),
                        borderRadius: 2,
                        margin: '4px auto',
                        width: '80%',
                      }}
                    />
                  </div>
                </Tooltip>
              );
            })}
            <div
              style={{
                ...CELL,
                background: DARK_THEME.darkAccent,
                textAlign: 'center',
                color: DARK_THEME.textMuted,
                fontWeight: 600,
              }}
            >
              Итого
            </div>
          </div>

          {/* Нормированные работы */}
          <div style={rowStyle({ borderTop: 'none' })}>
            <div style={{ ...CELL_LABEL, background: DARK_THEME.cardBg, fontWeight: 600, color: DARK_THEME.textPrimary, whiteSpace: 'nowrap' as const }}>
              Нормированные работы
            </div>
            {summary.roles.map((role) => (
              <div key={role} style={{ ...CELL, ...roleCellStyle(role), fontWeight: 600 }}>
                {Math.round(summary.total_by_role[role] ?? 0).toLocaleString('ru')}
              </div>
            ))}
            <div style={{ ...CELL, background: DARK_THEME.cardBg, fontWeight: 700, color: DARK_THEME.textPrimary }}>
              {Math.round(summary.total).toLocaleString('ru')}
            </div>
          </div>

          {/* Обязательные работы */}
          {summary.work_type_rows.map((row) => (
            <div key={row.work_type_id} style={rowStyle()}>
              <div
                style={{
                  ...CELL_LABEL,
                  background: DARK_THEME.darkAccent,
                  whiteSpace: 'nowrap' as const,
                }}
              >
                — {row.work_type_label}
              </div>
              {summary.roles.map((role) => {
                const h = row.by_role[role] ?? 0;
                const pct = row.by_role_pct[role];
                return (
                  <div key={role} style={{ ...CELL, ...roleCellStyle(role), color: DARK_THEME.textMuted }}>
                    {h > 0 ? Math.round(h).toLocaleString('ru') : '—'}
                    {pct != null && h > 0 && (
                      <span style={{ marginLeft: 4, fontSize: 10, color: DARK_THEME.textHint }}>
                        {pct}%
                      </span>
                    )}
                  </div>
                );
              })}
              <div style={{ ...CELL, background: DARK_THEME.darkAccent, color: DARK_THEME.textMuted }}>
                {Math.round(row.total).toLocaleString('ru')}
              </div>
            </div>
          ))}

          {/* На бэклог */}
          <div style={{ ...rowStyle({ borderTop: `2px solid ${DARK_THEME.cyanPrimary}` }) }}>
            <div
              style={{
                ...CELL_LABEL,
                background: 'rgba(0,201,200,0.08)',
                color: DARK_THEME.cyanPrimary,
                fontWeight: 700,
                fontSize: 16,
                borderLeft: `3px solid ${DARK_THEME.cyanPrimary}`,
                whiteSpace: 'nowrap' as const,
              }}
            >
              На бэклог
            </div>
            {summary.roles.map((role) => {
              const avail = summary.available_for_backlog_by_role[role] ?? 0;
              const used = roleDemand[role as keyof typeof roleDemand] ?? 0;
              const remaining = Math.round(avail - used);
              const isDeficit = remaining < 0;
              const isExternal = role === 'qa' && summary.external_qa_hours != null;
              const hasUsed = used > 0;
              return (
                <div
                  key={role}
                  style={{
                    ...CELL,
                    ...roleBorderStyle(role),
                    background: isDeficit ? 'rgba(255,165,0,0.08)' : 'rgba(0,201,200,0.1)',
                    color: isDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
                    fontWeight: 700,
                    fontSize: 17,
                    whiteSpace: 'nowrap' as const,
                  }}
                >
                  {hasUsed ? (
                    <>
                      {remaining.toLocaleString('ru')}
                      <span style={{ fontSize: 12, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
                        из {Math.round(avail).toLocaleString('ru')}
                      </span>
                    </>
                  ) : (
                    Math.round(avail).toLocaleString('ru')
                  )}
                  {isExternal && (
                    <span style={{ fontSize: 11, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
                      внешний
                    </span>
                  )}
                </div>
              );
            })}
            {(() => {
              const totalRemaining = Math.round(summary.available_for_backlog_total - totalDemand);
              const isTotalDeficit = totalRemaining < 0;
              return (
                <div
                  style={{
                    ...CELL,
                    background: isTotalDeficit ? 'rgba(255,165,0,0.08)' : 'rgba(0,201,200,0.08)',
                    color: isTotalDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
                    fontWeight: 700,
                    fontSize: 17,
                    whiteSpace: 'nowrap' as const,
                  }}
                >
                  {totalDemand > 0 ? (
                    <>
                      {totalRemaining.toLocaleString('ru')}
                      <span style={{ fontSize: 12, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
                        из {Math.round(summary.available_for_backlog_total).toLocaleString('ru')}
                      </span>
                    </>
                  ) : (
                    Math.round(summary.available_for_backlog_total).toLocaleString('ru')
                  )}
                </div>
              );
            })()}
          </div>
        </div>

        {/* Блок отпусков */}
        {summary.absence_days_by_employee.length > 0 && (
          <div style={{
            borderLeft: `2px solid ${DARK_THEME.border}`,
            background: DARK_THEME.darkAccent,
            minWidth: 180,
            maxWidth: 240,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
          }}>
            {/* Заголовок */}
            <div style={{
              padding: '8px 12px',
              borderBottom: `1px solid ${DARK_THEME.border}`,
              fontSize: 10,
              color: DARK_THEME.textMuted,
              textTransform: 'uppercase' as const,
              letterSpacing: 0.5,
              fontWeight: 600,
              background: DARK_THEME.cardBg,
            }}>
              Отпуска квартала
            </div>
            {/* Список сотрудников */}
            <div style={{ padding: '6px 12px', flex: 1 }}>
              {summary.absence_days_by_employee.map((emp) => {
                const roleColor = emp.role ? getRoleColor(roles, emp.role) : DARK_THEME.textDim;
                return (
                  <div key={emp.employee_id} style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '3px 0',
                    borderBottom: `1px solid rgba(255,255,255,0.04)`,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      <div style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: roleColor,
                        flexShrink: 0,
                      }} />
                      <span style={{
                        fontSize: 11,
                        color: DARK_THEME.textSecondary,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap' as const,
                      }}>
                        {emp.display_name}
                      </span>
                    </div>
                    <span style={{ fontSize: 11, fontFamily: FONTS.mono, color: DARK_THEME.textMuted, marginLeft: 8, flexShrink: 0 }}>
                      {emp.days > 0 ? `${emp.days} дн` : '—'}
                    </span>
                  </div>
                );
              })}
            </div>
            {/* Итого */}
            {(() => {
              const totalDays = summary.absence_days_by_employee.reduce((s, e) => s + e.days, 0);
              const totalVacHours = Math.round(
                Object.values(summary.calendar_gross_by_role).reduce((s, v) => s + v, 0) -
                Object.values(summary.total_by_role).reduce((s, v) => s + v, 0)
              );
              return totalDays > 0 ? (
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '6px 12px',
                  borderTop: `1px solid ${DARK_THEME.border}`,
                  fontSize: 11,
                }}>
                  <span style={{ color: DARK_THEME.textMuted }}>Итого</span>
                  <span style={{ fontFamily: FONTS.mono, color: DARK_THEME.textSecondary }}>
                    {totalDays} дн · −{totalVacHours} ч
                  </span>
                </div>
              ) : null;
            })()}
          </div>
        )}
      </div>
    </Card>
  );
}
