import React from 'react';
import { Card, Skeleton, Tooltip } from 'antd';
import { useScenarioResourceSummary } from '../../hooks/usePlanning';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel } from '../../utils/roles';
import { DARK_THEME, FONTS } from '../../utils/constants';

interface Props {
  scenarioId: string;
  enabled: boolean;
}

const CELL: React.CSSProperties = {
  padding: '7px 10px',
  textAlign: 'right' as const,
  fontFamily: FONTS.mono,
  fontSize: 12,
};

const CELL_LABEL: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 12,
  color: DARK_THEME.textMuted,
};

export default function ScenarioResourceSummary({ scenarioId, enabled }: Props) {
  const { data: summary, isLoading } = useScenarioResourceSummary(scenarioId, enabled);
  const { data: roles = [] } = useRoles();

  if (isLoading) {
    return (
      <Card styles={{ body: { padding: 14 } }}>
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (!summary || summary.roles.length === 0) return null;

  const gridCols = `180px repeat(${summary.roles.length}, 1fr) 90px`;

  const headerStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: gridCols,
    gap: 1,
    background: DARK_THEME.border,
    borderRadius: '6px 6px 0 0',
    overflow: 'hidden',
  };

  const rowStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: gridCols,
    gap: 1,
    background: DARK_THEME.border,
  };

  return (
    <Card styles={{ body: { padding: 0, overflow: 'hidden', borderRadius: 8 } }}>
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
                  background: DARK_THEME.darkAccent,
                  textAlign: 'center',
                  color: DARK_THEME.textSecondary,
                  cursor: 'default',
                }}
              >
                <div style={{ fontWeight: 600 }}>{label}</div>
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

      {/* Всего норма-часов */}
      <div style={rowStyle}>
        <div style={{ ...CELL_LABEL, background: DARK_THEME.cardBg, fontWeight: 600, color: DARK_THEME.textPrimary }}>
          Всего норма-часов
        </div>
        {summary.roles.map((role) => (
          <div key={role} style={{ ...CELL, background: DARK_THEME.cardBg, fontWeight: 600 }}>
            {Math.round(summary.total_by_role[role] ?? 0).toLocaleString('ru')}
          </div>
        ))}
        <div style={{ ...CELL, background: DARK_THEME.cardBg, fontWeight: 700, color: DARK_THEME.textPrimary }}>
          {Math.round(summary.total).toLocaleString('ru')}
        </div>
      </div>

      {/* Обязательные работы */}
      {summary.work_type_rows.map((row) => (
        <div key={row.work_type_id} style={rowStyle}>
          <div style={{ ...CELL_LABEL, background: DARK_THEME.darkAccent }}>
            — {row.work_type_label}
          </div>
          {summary.roles.map((role) => {
            const h = row.by_role[role] ?? 0;
            const pct = row.by_role_pct[role];
            return (
              <div key={role} style={{ ...CELL, background: DARK_THEME.darkAccent, color: DARK_THEME.textMuted }}>
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
      <div style={{ ...rowStyle, borderTop: `2px solid ${DARK_THEME.cyanPrimary}` }}>
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
          const isExternal = role === 'qa' && summary.external_qa_hours != null;
          return (
            <div
              key={role}
              style={{
                ...CELL,
                background: 'rgba(0,201,200,0.08)',
                color: DARK_THEME.cyanPrimary,
                fontWeight: 700,
              }}
            >
              {Math.round(avail).toLocaleString('ru')}
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
          {Math.round(summary.available_for_backlog_total).toLocaleString('ru')}
        </div>
      </div>
    </Card>
  );
}
