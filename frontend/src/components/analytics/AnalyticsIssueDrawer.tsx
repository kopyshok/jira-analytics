import { useState, useEffect } from 'react';
import { Drawer, Skeleton, Alert, Button, Tag } from 'antd';
import { useIssueContext } from '../../hooks/useIssueContext';
import { useCategories } from '../../hooks/useCategories';
import { useQueryClient } from '@tanstack/react-query';
import { statusTagColor } from '../../utils/status';
import IssueContextBlock from './IssueContextBlock';
import IssueCategorizer from './IssueCategorizer';
import AnalyticsWorklogsBlock from './AnalyticsWorklogsBlock';

const JIRA_BASE = 'https://itgri.atlassian.net/browse';

interface Props {
  issueId: string | null;
  issueKey: string | null;
  periodStart: string;
  periodEnd: string;
  onClose: () => void;
}

interface DrawerContentProps {
  issueId: string;
  issueKey: string;
  periodStart: string;
  periodEnd: string;
  onDrillDown: (id: string) => void;
  onSaved: () => void;
}

function DrawerContent({ issueId, periodStart, periodEnd, onDrillDown, onSaved }: DrawerContentProps) {
  const { data: context, isLoading, isError, refetch } = useIssueContext(issueId);
  const { items: categories } = useCategories();

  if (isLoading) {
    return (
      <div style={{ padding: '16px 20px' }}>
        <Skeleton active paragraph={{ rows: 6 }} />
      </div>
    );
  }

  if (isError || !context) {
    return (
      <div style={{ padding: '16px 20px' }}>
        <Alert
          type="error"
          title="Не удалось загрузить контекст задачи"
          action={<Button size="small" onClick={() => refetch()}>Повторить</Button>}
        />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '16px 20px' }}>
      <IssueContextBlock
        context={context}
        categories={categories}
        onDrillDown={onDrillDown}
        onChildSaved={onSaved}
      />
      <IssueCategorizer
        context={context}
        categories={categories}
        onSaved={onSaved}
      />
      {/* Worklogs section */}
      <div
        style={{
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 8,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: '#64748b',
            padding: '10px 14px 8px',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>Ворклоги за период</span>
          <span style={{ fontSize: 11, fontWeight: 500, letterSpacing: 0, textTransform: 'none', color: '#64748b' }}>
            {periodStart} – {periodEnd}
          </span>
        </div>
        <div style={{ padding: '8px 0' }}>
          <AnalyticsWorklogsBlock
            issueId={issueId}
            periodStart={periodStart}
            periodEnd={periodEnd}
          />
        </div>
      </div>
    </div>
  );
}

interface DrawerHeaderProps {
  issueId: string;
  issueKey: string;
  canGoBack: boolean;
  onBack: () => void;
  onClose: () => void;
}

function DrawerHeader({ issueId, issueKey, canGoBack, onBack, onClose }: DrawerHeaderProps) {
  const { data: context, isLoading } = useIssueContext(issueId);

  return (
    <div
      style={{
        padding: '16px 20px 14px',
        borderBottom: '1px solid rgba(255,255,255,0.1)',
        background: '#0d1c33',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        {canGoBack && (
          <Button
            size="small"
            type="text"
            onClick={onBack}
            style={{ color: '#94a3b8', padding: '0 6px', marginRight: 2 }}
          >
            ← назад
          </Button>
        )}
        <a
          href={`${JIRA_BASE}/${issueKey}`}
          target="_blank"
          rel="noreferrer"
          style={{
            fontFamily: 'monospace',
            fontSize: 13,
            fontWeight: 700,
            color: '#00c9c8',
            background: 'rgba(0,201,200,0.08)',
            border: '1px solid rgba(0,201,200,0.25)',
            borderRadius: 5,
            padding: '3px 8px',
            textDecoration: 'none',
            whiteSpace: 'nowrap',
          }}
        >
          {issueKey}
        </a>
        {!isLoading && context && (
          <Tag
            color={statusTagColor(context.status, context.status_category)}
            style={{ marginInlineEnd: 0, fontSize: 11, padding: '3px 9px' }}
          >
            {context.status}
          </Tag>
        )}
        <span
          onClick={onClose}
          style={{
            marginLeft: 'auto',
            width: 28,
            height: 28,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 6,
            color: '#64748b',
            fontSize: 18,
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          ×
        </span>
      </div>
      {isLoading ? (
        <Skeleton active title={{ width: 300 }} paragraph={false} />
      ) : context ? (
        <div style={{ fontSize: 13, fontWeight: 500, color: '#e6edf7', lineHeight: 1.4 }}>
          {context.summary}
        </div>
      ) : (
        <div style={{ fontSize: 13, color: '#94a3b8' }}>{issueKey}</div>
      )}
    </div>
  );
}

export default function AnalyticsIssueDrawer({
  issueId,
  issueKey,
  periodStart,
  periodEnd,
  onClose,
}: Props) {
  // Back-stack: stack of {id, key} entries. Current is top of stack.
  const [stack, setStack] = useState<Array<{ id: string; key: string }>>([]);
  const qc = useQueryClient();

  // Sync stack when external issueId changes
  useEffect(() => {
    if (issueId && issueKey) {
      setStack([{ id: issueId, key: issueKey }]);
    } else {
      setStack([]);
    }
  }, [issueId, issueKey]);

  const currentEntry = stack.length > 0 ? stack[stack.length - 1] : null;
  const open = !!currentEntry;

  const handleDrillDown = (childId: string) => {
    // We need to know the key — fetch from context or fallback to id prefix
    // We'll re-use the cached context data to get the key
    const parentContext = qc.getQueryData<{ children: Array<{ id: string; key: string }> }>(
      ['issue', 'context', currentEntry?.id],
    );
    const childKey =
      parentContext?.children?.find((c) => c.id === childId)?.key ??
      childId;
    setStack(prev => [...prev, { id: childId, key: childKey }]);
  };

  const handleBack = () => {
    setStack(prev => prev.slice(0, -1));
  };

  const handleClose = () => {
    setStack([]);
    onClose();
  };

  const handleSaved = () => {
    // Context will be invalidated by the child components
  };

  return (
    <Drawer
      open={open}
      onClose={handleClose}
      destroyOnClose={false}
      closable={false}
      styles={{
        header: { display: 'none' },
        body: { padding: 0, background: '#0f2340', display: 'flex', flexDirection: 'column' },
        wrapper: { width: 720, background: '#0f2340' },
      }}
      style={{ background: '#0f2340' }}
    >
      {currentEntry && (
        <>
          <DrawerHeader
            issueId={currentEntry.id}
            issueKey={currentEntry.key}
            canGoBack={stack.length > 1}
            onBack={handleBack}
            onClose={handleClose}
          />
          <div style={{ flex: 1, overflowY: 'auto', background: '#0f2340' }}>
            <DrawerContent
              key={currentEntry.id}
              issueId={currentEntry.id}
              issueKey={currentEntry.key}
              periodStart={periodStart}
              periodEnd={periodEnd}
              onDrillDown={handleDrillDown}
              onSaved={handleSaved}
            />
          </div>
        </>
      )}
    </Drawer>
  );
}
