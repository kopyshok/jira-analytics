import { memo, type CSSProperties } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Checkbox, InputNumber, Select, Tag } from 'antd';
import { HolderOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { AllocationOverridePopover } from './AllocationOverridePopover';
import BacklogRoleCell from './BacklogRoleCell';
import { effectiveEstimate } from '../../utils/allocationEstimates';
import { statusTagColor } from '../../utils/status';
import { getRoleColor } from '../../utils/roles';
import { OPO_COLOR } from '../../utils/opo';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { AllocationResponse, ResourceEmployee, Role } from '../../types/api';
import type { ContinuationInfoRow } from '../../api/planning';

export type BacklogAllocRowProps = {
  alloc: AllocationResponse;
  scenarioId: string;
  scenarioStatus: 'draft' | 'approved';
  isDraft: boolean;
  compact: boolean;
  flashing: boolean;
  rowStateClass: string;
  gridTemplate: string;
  gridGap: number;
  continuationInfo: ContinuationInfoRow | undefined;
  employees: ResourceEmployee[] | undefined;
  roles: Role[];
  jiraBaseUrl: string;
  resourceTotalForBacklog: number;
  registerRef: (el: HTMLDivElement | null) => void;
  onToggle: (a: AllocationResponse) => void;
  onPriorityChange: (backlogItemId: string, priority: number | null) => void;
  onAssigneeChange: (allocId: string, employeeId: string | null) => void;
  onOpenBreakdown: (issueId: string, issueKey: string) => void;
};

function BacklogAllocRowBase({
  alloc: a,
  scenarioId,
  scenarioStatus,
  isDraft,
  compact,
  flashing,
  rowStateClass,
  gridTemplate,
  gridGap,
  continuationInfo,
  employees,
  roles,
  jiraBaseUrl,
  resourceTotalForBacklog,
  registerRef,
  onToggle,
  onPriorityChange,
  onAssigneeChange,
  onOpenBreakdown,
}: BacklogAllocRowProps) {
  const { setNodeRef, transform, transition, isDragging, attributes, listeners } = useSortable({ id: a.id });

  const eff = effectiveEstimate(a);
  const an = eff.analyst;
  const de = eff.dev;
  const qa = eff.qa;
  const op = eff.opo;
  const total = an + de + qa + op;
  const priorityCyan = a.priority != null && a.priority <= 3;
  const hasOverride =
    a.override_estimate_analyst_hours !== null ||
    a.override_estimate_dev_hours !== null ||
    a.override_estimate_qa_hours !== null ||
    a.override_estimate_opo_hours !== null;
  const isPendingContinuation = !!continuationInfo?.is_continuation && !hasOverride;

  const className = ['backlog-row', flashing ? 'cyan-flash' : '', rowStateClass]
    .filter(Boolean)
    .join(' ');

  // Мягкая подсветка отмеченных: лёгкий cyan-фон + 3px акцентная полоса слева.
  // Неотмеченные — прозрачный фон, opacity 0.85 (чуть выше чем было 0.7 — для
  // читаемости при демо без визуального шума).
  const style: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: gridTemplate,
    columnGap: gridGap,
    padding: compact ? '4px 14px' : '12px 14px',
    fontSize: compact ? 13 : 14,
    borderBottom: `1px solid ${DARK_THEME.border}`,
    alignItems: 'center',
    cursor: isDraft ? 'pointer' : 'default',
    background: a.included
      ? 'var(--row-included-bg, rgba(0,201,200,0.06))'
      : 'transparent',
    borderLeft: a.included
      ? '3px solid var(--accent-1, #00c9c8)'
      : '3px solid transparent',
    opacity: a.included ? 1 : 0.85,
    transform: CSS.Translate.toString(transform),
    transition,
    ...(isDragging ? { opacity: 0.5 } : null),
  };

  return (
    <div
      ref={(el) => {
        setNodeRef(el);
        registerRef(el);
      }}
      onClick={() => onToggle(a)}
      className={className}
      style={style}
    >
      <span
        {...(isDraft ? attributes : {})}
        {...(isDraft ? listeners : {})}
        onClick={(e) => e.stopPropagation()}
        title={isDraft ? 'Перетащить' : ''}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: isDraft ? 'grab' : 'default',
          color: DARK_THEME.textMuted,
          opacity: isDraft ? 1 : 0.3,
          touchAction: 'none',
        }}
      >
        <HolderOutlined />
      </span>
      <div onClick={(e) => e.stopPropagation()}>
        <Checkbox checked={a.included} disabled={!isDraft} onChange={() => onToggle(a)} />
      </div>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <InputNumber
          min={1}
          max={10}
          value={a.priority}
          variant="borderless"
          size="small"
          controls={false}
          style={{
            width: 36,
            height: 24,
            borderRadius: 4,
            fontSize: 11,
            fontWeight: 700,
            fontFamily: FONTS.mono,
            color: priorityCyan ? '#003a3a' : DARK_THEME.textMuted,
            background: priorityCyan ? DARK_THEME.cyanPrimary : DARK_THEME.darkAccent,
            padding: 0,
            textAlign: 'center',
          }}
          className="backlog-priority-input"
          placeholder="—"
          onKeyDown={(e) => {
            if (e.key === 'Escape') (e.target as HTMLInputElement).blur();
          }}
          onBlur={(e) => {
            const raw = e.target.value;
            const parsed = raw === '' ? null : parseInt(raw, 10);
            const next = parsed === null || isNaN(parsed) ? null : Math.min(10, Math.max(1, parsed));
            if (next !== a.priority) onPriorityChange(a.backlog_item_id, next);
          }}
        />
      </div>
      <div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            color: DARK_THEME.textPrimary,
            fontSize: 14,
            marginBottom: 3,
          }}
        >
          <span style={{ flex: '1 1 auto', minWidth: 0 }}>{a.title}</span>
          {hasOverride && (
            <Tag color="gold" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>
              переоценка
            </Tag>
          )}
          {isPendingContinuation && (
            <Tag color="red" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>
              ⚠ продолжение
            </Tag>
          )}
          <AllocationOverridePopover
            scenarioId={scenarioId}
            allocationId={a.id}
            scenarioStatus={scenarioStatus}
            currentOverride={{
              analyst: a.override_estimate_analyst_hours,
              dev: a.override_estimate_dev_hours,
              qa: a.override_estimate_qa_hours,
              opo: a.override_estimate_opo_hours,
            }}
            continuation={continuationInfo}
          />
        </div>
        {a.status && (
          <Tag
            color={statusTagColor(a.status, a.status_category)}
            style={{ fontSize: 10, margin: '2px 4px 0 0', padding: '0 4px' }}
          >
            {a.status}
          </Tag>
        )}
        {a.jira_key &&
          (jiraBaseUrl ? (
            <a
              href={`${jiraBaseUrl}/browse/${a.jira_key}`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              style={{ fontFamily: FONTS.mono, fontSize: 11, color: DARK_THEME.cyanSecondary }}
            >
              {a.jira_key}
            </a>
          ) : (
            <span style={{ fontFamily: FONTS.mono, fontSize: 11, color: DARK_THEME.cyanSecondary }}>
              {a.jira_key}
            </span>
          ))}
        {a.has_children_in_backlog && a.issue_id && (
          <InfoCircleOutlined
            onClick={(e) => {
              e.stopPropagation();
              onOpenBreakdown(a.issue_id!, a.jira_key ?? '');
            }}
            style={{ marginLeft: 6, cursor: 'pointer', color: '#38bdf8', fontSize: 13 }}
          />
        )}
        {a.cost_type && (
          <Tag
            color={a.cost_type.toLowerCase().includes('change') ? 'blue' : 'green'}
            style={{ fontSize: 10, padding: '0 4px', marginLeft: 4 }}
          >
            {a.cost_type}
          </Tag>
        )}
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        {!isDraft && !a.assignee_employee_id ? (
          <span style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
            {a.assignee_display_name ?? '—'}
          </span>
        ) : (
          <Select
            size="small"
            value={a.assignee_employee_id ?? undefined}
            placeholder={a.assignee_display_name ?? '—'}
            allowClear
            disabled={!isDraft}
            style={{ width: '100%', fontSize: 12 }}
            options={
              employees?.map((emp) => ({
                label: emp.display_name,
                value: emp.employee_id,
              })) ?? []
            }
            onChange={(value: string | undefined) => onAssigneeChange(a.id, value ?? null)}
          />
        )}
      </div>
      <div
        style={{
          fontSize: 12,
          color: DARK_THEME.textMuted,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {a.customer ?? '—'}
      </div>
      <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
        <BacklogRoleCell label="АН" hours={an} total={total} color={getRoleColor(roles, 'analyst')} />
        <BacklogRoleCell label="ПР" hours={de} total={total} color={getRoleColor(roles, 'dev')} />
        <BacklogRoleCell label="ТС" hours={qa} total={total} color={getRoleColor(roles, 'qa')} />
        <BacklogRoleCell label="ОПЭ" hours={op} total={total} color={OPO_COLOR} />
      </div>
      <div style={{ textAlign: 'right' }}>
        <span style={{ fontFamily: FONTS.mono, fontSize: 14, color: DARK_THEME.textPrimary }}>
          {Math.round(total)} ч
        </span>
        {resourceTotalForBacklog > 0 && (
          <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 1 }}>
            {Math.round((total / resourceTotalForBacklog) * 100)}% ресурса
          </div>
        )}
      </div>
    </div>
  );
}

const BacklogAllocRow = memo(BacklogAllocRowBase);
export default BacklogAllocRow;
