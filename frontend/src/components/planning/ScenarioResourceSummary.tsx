import React, { useMemo, useState } from 'react';
import { Card, Skeleton, Tooltip } from 'antd';
import { useScenarioResourceSummary } from '../../hooks/usePlanning';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel, getRoleColor } from '../../utils/roles';
import { DARK_THEME, FONTS } from '../../utils/constants';
import { demandByRole } from '../../utils/planning';
import type { AllocationResponse } from '../../types/api';

interface Props {
  scenarioId: string;
  enabled: boolean;
  allocations?: AllocationResponse[];
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

export default function ScenarioResourceSummary({ scenarioId, enabled, allocations }: Props) {
  const { data: summary, isLoading } = useScenarioResourceSummary(scenarioId, enabled);
  const { data: roles = [] } = useRoles();

  // Потребность по ролям от отмеченных элементов (analyst/dev/qa с учётом opo_analyst_ratio)
  const roleDemand = useMemo(
    () => (allocations ? demandByRole(allocations) : { analyst: 0, dev: 0, qa: 0 }),
    [allocations],
  );

  if (isLoading) {
    return (
      <Card styles={{ body: { padding: 14 } }}>
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (!summary || summary.roles.length === 0) return null;

  const gridCols = `180px repeat(${summary.roles.length}, 1fr) 90px`;

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
                    <div style={{ fontWeight: 600, color: getRoleColor(roles, role) }}>{label}</div>
                    <div
                      style={{
                        height: 3,
                        background: getRoleColor(roles, role),
                        borderRadius: 2,
                        margin: '4px auto',
                        width: '80%',
                      }}
                    />
                    <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 2 }}>
                      {names.length} чел. ⓘ
                    </div>
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
            <div style={{ ...CELL_LABEL, background: DARK_THEME.cardBg, fontWeight: 600, color: DARK_THEME.textPrimary }}>
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
              <Tooltip title={row.work_type_label}>
                <div
                  style={{
                    ...CELL_LABEL,
                    background: DARK_THEME.darkAccent,
                    maxWidth: 140,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  — {row.work_type_label}
                </div>
              </Tooltip>
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
                borderLeft: `3px solid ${DARK_THEME.cyanPrimary}`,
              }}
            >
              На бэклог
            </div>
            {summary.roles.map((role) => {
              const avail = summary.available_for_backlog_by_role[role] ?? 0;
              const used = roleDemand[role as keyof typeof roleDemand] ?? 0;
              const remaining = Math.round(Math.max(0, avail - used));
              const isExternal = role === 'qa' && summary.external_qa_hours != null;
              const hasUsed = used > 0;
              return (
                <div
                  key={role}
                  style={{
                    ...CELL,
                    ...roleBorderStyle(role),
                    background: 'rgba(0,201,200,0.1)',
                    color: DARK_THEME.cyanPrimary,
                    fontWeight: 700,
                  }}
                >
                  {hasUsed ? (
                    <>
                      {remaining.toLocaleString('ru')}
                      <div style={{ fontSize: 10, color: DARK_THEME.textHint, fontWeight: 400, marginTop: 1 }}>
                        из {Math.round(avail).toLocaleString('ru')}
                      </div>
                    </>
                  ) : (
                    Math.round(avail).toLocaleString('ru')
                  )}
                  {isExternal && (
                    <div style={{ fontSize: 10, color: DARK_THEME.textHint, fontWeight: 400 }}>
                      внешний
                    </div>
                  )}
                </div>
              );
            })}
            <div
              style={{
                ...CELL,
                background: 'rgba(0,201,200,0.08)',
                color: DARK_THEME.cyanPrimary,
                fontWeight: 700,
              }}
            >
              {totalDemand > 0 ? (
                <>
                  {Math.round(Math.max(0, summary.available_for_backlog_total - totalDemand)).toLocaleString('ru')}
                  <div style={{ fontSize: 10, color: DARK_THEME.textHint, fontWeight: 400, marginTop: 1 }}>
                    из {Math.round(summary.available_for_backlog_total).toLocaleString('ru')}
                  </div>
                </>
              ) : (
                Math.round(summary.available_for_backlog_total).toLocaleString('ru')
              )}
            </div>
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
