import { useState } from 'react';
import { Badge, Button, Collapse, Select, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import { useManualClassify } from '../../hooks/useWorkTypeReport';
import { DARK_THEME } from '../../utils/constants';
import type { ManualReviewIssue, ThemeOut } from '../../types/workTypeReport';

interface Props {
  items: ManualReviewIssue[];
  workTypeId: string;
  themes: ThemeOut[];
}

interface RowState {
  themeId: string | null;
  saving: boolean;
}

export default function ManualReviewBlock({ items, workTypeId, themes }: Props) {
  const classify = useManualClassify();
  const [rowState, setRowState] = useState<Record<string, RowState>>({});
  const [processedIssueIds, setProcessedIssueIds] = useState<Set<string>>(new Set());

  if (items.length === 0) return null;

  const getRowState = (issueId: string): RowState =>
    rowState[issueId] ?? { themeId: null, saving: false };

  const setThemeId = (issueId: string, themeId: string | null) => {
    setRowState((prev) => ({
      ...prev,
      [issueId]: { ...(prev[issueId] ?? { themeId: null, saving: false }), themeId },
    }));
  };

  const handleAssign = (issueId: string) => {
    const state = getRowState(issueId);
    if (!state.themeId) return;
    setRowState((prev) => ({
      ...prev,
      [issueId]: { ...(prev[issueId] ?? { themeId: null, saving: false }), saving: true },
    }));
    classify.mutate(
      { issue_id: issueId, work_type_id: workTypeId, theme_id: state.themeId },
      {
        onSuccess: () => {
          setProcessedIssueIds((prev) => new Set([...prev, issueId]));
        },
        onSettled: () => {
          setRowState((prev) => ({
            ...prev,
            [issueId]: { ...(prev[issueId] ?? { themeId: null, saving: false }), saving: false },
          }));
        },
      },
    );
  };

  const themeOptions = themes.map((t) => ({ value: t.id, label: t.name }));

  const columns: ColumnsType<ManualReviewIssue> = [
    {
      title: 'Задача',
      key: 'key',
      width: 100,
      render: (_, row) => (
        <span style={{ fontFamily: 'monospace', fontSize: 12, color: DARK_THEME.cyanPrimary, fontWeight: 600 }}>
          {row.key}
        </span>
      ),
    },
    {
      title: 'Название',
      key: 'summary',
      render: (_, row) => (
        <span style={{ fontSize: 12, color: DARK_THEME.textSecondary }}>
          {row.summary}
        </span>
      ),
    },
    {
      title: 'Часы',
      key: 'hours',
      width: 70,
      align: 'right' as const,
      render: (_, row) => (
        <span style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
          {Math.round(row.hours)}
        </span>
      ),
    },
    {
      title: 'Причина',
      key: 'failure_reason',
      width: 160,
      render: (_, row) => (
        <span style={{ fontSize: 11, color: DARK_THEME.amber }}>{row.failure_reason}</span>
      ),
    },
    {
      title: 'Тема',
      key: 'theme',
      width: 180,
      render: (_, row) => {
        const state = getRowState(row.issue_id);
        const isProcessed = processedIssueIds.has(row.issue_id);
        return (
          <Select
            placeholder="Тема"
            size="small"
            style={{ width: '100%' }}
            value={state.themeId}
            onChange={(v) => setThemeId(row.issue_id, v)}
            options={themeOptions}
            disabled={state.saving || isProcessed}
          />
        );
      },
    },
    {
      title: '',
      key: 'action',
      width: 90,
      render: (_, row) => {
        const state = getRowState(row.issue_id);
        const isProcessed = processedIssueIds.has(row.issue_id);
        return (
          <Button
            size="small"
            type="primary"
            loading={state.saving}
            disabled={!state.themeId || isProcessed}
            onClick={() => handleAssign(row.issue_id)}
          >
            {isProcessed ? 'Готово' : 'Назначить'}
          </Button>
        );
      },
    },
  ];

  const header = (
    <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: DARK_THEME.textSecondary }}>
      <Badge color="red" />
      Требуют ручной классификации ({items.length})
    </span>
  );

  return (
    <div style={{ marginTop: 8 }}>
      <Collapse
        size="small"
        items={[{
          key: 'manual-review',
          label: header,
          children: (
            <>
              <Table<ManualReviewIssue>
                dataSource={items}
                columns={columns}
                rowKey="issue_id"
                pagination={false}
                size="small"
                style={{ background: DARK_THEME.cardBg }}
                rowClassName={(row) =>
                  processedIssueIds.has(row.issue_id) ? 'manual-review-processed' : ''
                }
              />
              <style>{`.manual-review-processed td { opacity: 0.5; }`}</style>
            </>
          ),
        }]}
        style={{
          background: DARK_THEME.darkAccent,
          border: `1px solid ${DARK_THEME.border}`,
          borderRadius: 6,
        }}
      />
    </div>
  );
}
