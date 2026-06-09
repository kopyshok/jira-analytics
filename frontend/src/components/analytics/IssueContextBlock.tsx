import React, { useState } from 'react';
import { Popover, Skeleton, Select, Checkbox, Tooltip, Tag } from 'antd';
import type { IssueContextAncestor, IssueContextChild, IssueContextResponse } from '../../types/api';
import type { CategoryResponse } from '../../types/api';
import { useIssueChildren } from '../../hooks/useIssueChildren';
import { setIssueCategory, setIssueInclude } from '../../api/issues';
import { useQueryClient } from '@tanstack/react-query';
import { statusTagColor } from '../../utils/status';

const CARD_BG = 'var(--mini-tile-bg, rgba(255,255,255,0.03))';
const CARD_BORDER = '1px solid var(--glass-border, rgba(255,255,255,0.08))';

interface BreadcrumbsProps {
  ancestors: IssueContextAncestor[];
  currentKey: string;
  currentSummary: string;
  currentIssueType: string;
  siblingsTotal: number;
  parentId: string | undefined;
  onDrillDown: (id: string) => void;
}

function SiblingPopover({
  parentId,
  count,
  onDrillDown,
}: {
  parentId: string;
  count: number;
  onDrillDown: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useIssueChildren(parentId, open);

  const content = (
    <div style={{ maxHeight: 300, overflowY: 'auto', minWidth: 200 }}>
      {isLoading && <Skeleton active paragraph={{ rows: 3 }} />}
      {data?.map((sib) => (
        <div
          key={sib.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '5px 0',
            borderBottom: '1px solid var(--glass-border, rgba(255,255,255,0.05))',
            cursor: 'pointer',
          }}
          onClick={() => { setOpen(false); onDrillDown(sib.id); }}
        >
          <span
            style={{
              fontFamily: 'monospace',
              fontSize: 11,
              color: 'var(--accent-1, #00c9c8)',
              background: 'var(--key-chip-bg, rgba(0,201,200,0.08))',
              border: '1px solid var(--key-chip-border, rgba(0,201,200,0.18))',
              borderRadius: 4,
              padding: '1px 5px',
              whiteSpace: 'nowrap',
            }}
          >
            {sib.key}
          </span>
          <span style={{ color: 'var(--text-muted, #94a3b8)', fontSize: 12, flex: 1 }}>{sib.summary}</span>
        </div>
      ))}
    </div>
  );

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      content={content}
      title={`Соседние задачи (${count})`}
      trigger="click"
      placement="bottomLeft"
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 3,
          fontSize: 10,
          color: 'var(--text-muted, #64748b)',
          background: 'rgba(100,116,139,0.1)',
          border: '1px solid rgba(100,116,139,0.15)',
          borderRadius: 10,
          padding: '2px 8px',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
          marginLeft: 4,
        }}
      >
        +{count - 1} соседей ▾
      </span>
    </Popover>
  );
}

interface TreeRowProps {
  level: number;
  isLast: boolean;
  isCurrent: boolean;
  issueKey: string;
  summary: string;
  issueType: string;
  onClick?: () => void;
  rightSlot?: React.ReactNode;
}

function TreeRow({
  level,
  isLast,
  isCurrent,
  issueKey,
  summary,
  issueType,
  onClick,
  rightSlot,
}: TreeRowProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 6,
        padding: '4px 6px',
        paddingLeft: 6 + level * 18,
        borderRadius: 4,
        cursor: onClick ? 'pointer' : 'default',
        background: isCurrent ? 'var(--key-chip-bg, rgba(0,201,200,0.06))' : 'transparent',
        border: isCurrent
          ? '1px solid var(--key-chip-border, rgba(0,201,200,0.2))'
          : '1px solid transparent',
      }}
      onClick={onClick}
    >
      {level > 0 && (
        <span
          style={{
            color: '#334155',
            fontSize: 12,
            fontFamily: 'monospace',
            lineHeight: '18px',
            flexShrink: 0,
          }}
        >
          {isLast ? '└' : '├'}
        </span>
      )}
      <span
        style={{
          fontFamily: 'monospace',
          fontSize: 11,
          color: 'var(--accent-1, #00c9c8)',
          background: 'var(--key-chip-bg, rgba(0,201,200,0.08))',
          border: '1px solid var(--key-chip-border, rgba(0,201,200,0.18))',
          borderRadius: 4,
          padding: '1px 5px',
          whiteSpace: 'nowrap',
          flexShrink: 0,
          lineHeight: '16px',
        }}
      >
        {issueKey}
      </span>
      <span
        style={{
          fontSize: 10,
          color: 'var(--text-muted, #475569)',
          fontStyle: 'italic',
          flexShrink: 0,
          lineHeight: '18px',
        }}
      >
        {issueType}
      </span>
      <span
        style={{
          fontSize: 12,
          color: isCurrent ? 'var(--text, #e6edf7)' : '#cbd5e1',
          fontWeight: isCurrent ? 600 : 400,
          flex: '1 1 auto',
          minWidth: 0,
          wordBreak: 'break-word',
          lineHeight: 1.45,
        }}
      >
        {summary}
      </span>
      {rightSlot && <span style={{ flexShrink: 0 }}>{rightSlot}</span>}
    </div>
  );
}

function Breadcrumbs({
  ancestors,
  currentKey,
  currentSummary,
  currentIssueType,
  siblingsTotal,
  parentId,
  onDrillDown,
}: BreadcrumbsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 12 }}>
      {ancestors.map((anc, idx) => {
        const isParent = idx === ancestors.length - 1;
        return (
          <TreeRow
            key={anc.id}
            level={idx}
            isLast={false}
            isCurrent={false}
            issueKey={anc.key}
            summary={anc.summary}
            issueType={anc.issue_type}
            onClick={() => onDrillDown(anc.id)}
            rightSlot={
              isParent && siblingsTotal > 1 && parentId ? (
                <SiblingPopover
                  parentId={parentId}
                  count={siblingsTotal}
                  onDrillDown={onDrillDown}
                />
              ) : null
            }
          />
        );
      })}
      <TreeRow
        level={ancestors.length}
        isLast={true}
        isCurrent
        issueKey={currentKey}
        summary={currentSummary}
        issueType={currentIssueType}
      />
    </div>
  );
}

interface ChildRowProps {
  child: IssueContextChild;
  categories: CategoryResponse[];
  onDrillDown: (id: string) => void;
  onSaved: () => void;
}

const ARCHIVE_CODES = new Set(['archive', 'archive_target']);

function ChildRow({ child, categories, onDrillDown, onSaved }: ChildRowProps) {
  const qc = useQueryClient();
  const isArchive = ARCHIVE_CODES.has(child.assigned_category ?? '');

  const handleCategoryChange = async (code: string | null) => {
    await setIssueCategory(child.id, code);
    qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    qc.invalidateQueries({ queryKey: ['analytics-report'] });
    qc.invalidateQueries({ queryKey: ['issue', 'context', child.id] });
    onSaved();
  };

  const handleIncludeChange = async (checked: boolean) => {
    await setIssueInclude(child.id, checked);
    qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    qc.invalidateQueries({ queryKey: ['analytics-report'] });
    qc.invalidateQueries({ queryKey: ['issue', 'context', child.id] });
    onSaved();
  };

  return (
    <tr>
      <td style={{ padding: '6px 8px', borderBottom: '1px solid rgba(255,255,255,0.04)', verticalAlign: 'middle' }}>
        <span
          style={{
            fontFamily: 'monospace',
            fontSize: 11,
            color: '#00c9c8',
            background: 'rgba(0,201,200,0.08)',
            border: '1px solid rgba(0,201,200,0.18)',
            borderRadius: 4,
            padding: '1px 5px',
            whiteSpace: 'nowrap',
            cursor: 'pointer',
          }}
          onClick={() => onDrillDown(child.id)}
        >
          {child.key}
        </span>
      </td>
      <td style={{
        padding: '6px 8px',
        borderBottom: '1px solid rgba(255,255,255,0.04)',
        maxWidth: 140,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        color: '#e2e8f0',
        fontSize: 12,
        verticalAlign: 'middle',
      }}>
        <Tooltip title={child.summary}>{child.summary}</Tooltip>
      </td>
      <td style={{ padding: '6px 8px', borderBottom: '1px solid rgba(255,255,255,0.04)', verticalAlign: 'middle' }}>
        <Tag
          color={statusTagColor(child.status, child.status_category)}
          style={{ marginInlineEnd: 0, fontSize: 10, padding: '2px 7px' }}
        >
          {child.status}
        </Tag>
      </td>
      <td style={{ padding: '6px 8px', borderBottom: '1px solid rgba(255,255,255,0.04)', verticalAlign: 'middle' }}>
        <Select
          size="small"
          value={child.assigned_category ?? null}
          onChange={handleCategoryChange}
          allowClear
          placeholder="Без категории"
          style={{ width: 140, fontSize: 11 }}
          options={categories.map(c => ({ value: c.code, label: c.label }))}
        />
      </td>
      <td style={{ padding: '6px 8px', borderBottom: '1px solid rgba(255,255,255,0.04)', textAlign: 'center', verticalAlign: 'middle' }}>
        <Tooltip title={isArchive ? 'Снимается автоматически архивной категорией' : undefined}>
          <Checkbox
            checked={child.include_in_analysis}
            disabled={isArchive}
            onChange={e => handleIncludeChange(e.target.checked)}
          />
        </Tooltip>
      </td>
    </tr>
  );
}

interface Props {
  context: IssueContextResponse;
  categories: CategoryResponse[];
  onDrillDown: (id: string) => void;
  onChildSaved: () => void;
}

export default function IssueContextBlock({ context, categories, onDrillDown, onChildSaved }: Props) {
  const parentId = context.ancestors.length > 0
    ? context.ancestors[context.ancestors.length - 1].id
    : undefined;

  return (
    <div
      style={{
        background: CARD_BG,
        border: CARD_BORDER,
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      {/* Section header */}
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--text-muted, #64748b)',
          padding: '10px 14px 8px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
        }}
      >
        Контекст
      </div>
      <div style={{ padding: '12px 14px' }}>
        <Breadcrumbs
          ancestors={context.ancestors}
          currentKey={context.key}
          currentSummary={context.summary}
          currentIssueType={context.issue_type}
          siblingsTotal={context.siblings_total}
          parentId={parentId}
          onDrillDown={onDrillDown}
        />
        <div style={{ height: 1, background: 'rgba(255,255,255,0.06)', margin: '4px 0 10px' }} />

        {/* Children table */}
        {context.children.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--text-muted, #475569)', fontStyle: 'italic', padding: '8px 0 2px' }}>
            У задачи нет подзадач
          </p>
        ) : (
          <>
            <div style={{
              fontSize: 11,
              fontWeight: 600,
              color: 'var(--text-muted, #64748b)',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              marginBottom: 6,
            }}>
              Подзадачи ({context.children.length})
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  {['Ключ', 'Название', 'Статус', 'Категория', 'В анализ'].map(h => (
                    <th
                      key={h}
                      style={{
                        color: 'var(--text-muted, #475569)',
                        fontWeight: 500,
                        textAlign: h === 'В анализ' ? 'center' : 'left',
                        padding: '5px 8px',
                        borderBottom: '1px solid rgba(255,255,255,0.07)',
                        fontSize: 10,
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {context.children.map(child => (
                  <ChildRow
                    key={child.id}
                    child={child}
                    categories={categories}
                    onDrillDown={onDrillDown}
                    onSaved={onChildSaved}
                  />
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
