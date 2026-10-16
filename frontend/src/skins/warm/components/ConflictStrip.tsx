import { useState } from 'react';
import { Button, Segmented, Tag } from 'antd';
import { WarningOutlined, ClockCircleOutlined } from '@ant-design/icons';
import type { ConflictOut } from '../../../api/resourcePlanning';
import { ConflictAlert } from '../../../components/resource-planning/ConflictPanel';
import {
  STATUS_LABEL, TYPE_LABELS, useConflictList, type ConflictGroupBy,
} from '../../../components/resource-planning/conflictList';

interface Props {
  conflicts: ConflictOut[];
  planId: string | null;
  onSelectAssignment?: (assignmentId: string) => void;
}

const SEVERITY_RANK: Record<string, number> = { critical: 0, warning: 1, info: 2 };
const plural = (n: number, one: string, few: string, many: string) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
};

/**
 * Конфликты плана в раскладке «Тёплая»: шапка со счётчиками и группировкой,
 * строка из первых конфликтов (щелчок открывает фазу в панели назначения) и
 * «Подробности» — полный список по группам с расшифровкой и сменой статуса.
 */
export default function ConflictStrip({ conflicts, planId, onSelectAssignment }: Props) {
  const list = useConflictList(conflicts, planId);
  const [collapsed, setCollapsed] = useState(false);
  const [details, setDetails] = useState(false);
  const { active, hidden, groups, criticals, warnings, groupBy, setGroupBy, showHidden, setShowHidden, handleStatusChange } = list;
  if (active.length === 0 && hidden.length === 0) return null;

  const top = [...active].sort((a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3)).slice(0, 3);

  return (
    <section className="wr-card wr-conflicts" aria-label="Конфликты">
      <div className="wr-row wr-row-between">
        <div className="wr-row" style={{ gap: 10 }}>
          <button
            type="button"
            className="wr-icon-plain"
            aria-label={collapsed ? 'Развернуть конфликты' : 'Свернуть конфликты'}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed(v => !v)}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d={collapsed ? 'M9 6l6 6-6 6' : 'M6 9l6 6 6-6'} />
            </svg>
          </button>
          <h2 className="rpc-card-title">Конфликты</h2>
          {criticals.length > 0 && (
            <span className="wr-pill is-bad">{criticals.length} {plural(criticals.length, 'критический', 'критических', 'критических')}</span>
          )}
          {warnings.length > 0 && (
            <span className="wr-pill is-warn">{warnings.length} {plural(warnings.length, 'предупреждение', 'предупреждения', 'предупреждений')}</span>
          )}
          {active.length === 0 && <span className="wr-muted">активных нет</span>}
        </div>
        <div className="wr-row" style={{ gap: 12 }}>
          <Segmented
            size="small"
            value={groupBy}
            onChange={(v) => { setGroupBy(v as ConflictGroupBy); setDetails(true); setCollapsed(false); }}
            options={[
              { label: 'По задачам', value: 'item' },
              { label: 'По сотрудникам', value: 'employee' },
              { label: 'По типу', value: 'type' },
            ]}
          />
          <button type="button" className="wr-link" aria-expanded={details} onClick={() => { setDetails(v => !v); setCollapsed(false); }}>
            {details ? 'Скрыть подробности' : 'Подробности'}
          </button>
        </div>
      </div>

      {!collapsed && !details && top.length > 0 && (
        <div className="wr-conflict-chips">
          {top.map(c => {
            const warn = c.severity !== 'critical';
            const clickable = !!c.assignment_id && !!onSelectAssignment;
            const context = [c.employee_name, c.backlog_item_title].filter(Boolean).join(' · ') || c.message;
            return (
              <div
                key={c.id}
                className={`wr-conflict-chip${warn ? ' is-warn' : ''}${clickable ? ' is-clickable' : ''}`}
                role={clickable ? 'button' : undefined}
                tabIndex={clickable ? 0 : undefined}
                title={c.message}
                onClick={() => clickable && onSelectAssignment?.(c.assignment_id!)}
                onKeyDown={(e) => {
                  if (clickable && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    onSelectAssignment?.(c.assignment_id!);
                  }
                }}
              >
                {warn ? <ClockCircleOutlined aria-hidden /> : <WarningOutlined aria-hidden />}
                <b>{TYPE_LABELS[c.type] ?? 'Конфликт'}</b>
                <span className="wr-conflict-ctx">{context}</span>
                <span className={`wr-pill is-sm ${c.status === 'open' ? 'is-bad' : 'is-neutral'}`}>{STATUS_LABEL[c.status]}</span>
              </div>
            );
          })}
        </div>
      )}

      {!collapsed && details && (
        <div className="wr-conflict-details">
          {hidden.length > 0 && (
            <Button size="small" type="link" style={{ padding: 0, fontSize: 12, alignSelf: 'flex-start' }} onClick={() => setShowHidden(!showHidden)}>
              {showHidden ? 'Скрыть погашенные' : `Показать ${hidden.length} погашенных`}
            </Button>
          )}
          {groups.map(g => (
            <div key={g.key} className="wr-conflict-group">
              <div className="wr-conflict-group-title">{g.label} <Tag>{g.items.length}</Tag></div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {g.items.map(c => (
                  <ConflictAlert
                    key={c.id}
                    conflict={c}
                    planId={planId}
                    onSelectAssignment={onSelectAssignment}
                    onStatusChange={handleStatusChange}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
