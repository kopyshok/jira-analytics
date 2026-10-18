import { useState, type ReactNode } from 'react';
import { Drawer, Skeleton, Alert, Button, Tag } from 'antd';
import { useIssueContext } from '../../hooks/useIssueContext';
import { useCategories } from '../../hooks/useCategories';
import { useQueryClient } from '@tanstack/react-query';
import { statusTagColor } from '../../utils/status';
import IssueContextBlock from './IssueContextBlock';
import IssueCategorizer from './IssueCategorizer';
import AnalyticsWorklogsBlock from './AnalyticsWorklogsBlock';
import JiraIssueLink from '../shared/JiraIssueLink';
import DetailSheet from '../common/DetailSheet';
import { useSkin } from '../../contexts/ThemeContext';
import { isoDateToRu } from '../../utils/format';


interface Props {
  issueId: string | null;
  issueKey: string | null;
  periodStart: string;
  periodEnd: string;
  onClose: () => void;
  /**
   * Панель подробностей — лист снизу или широкая справа (скин «Цветовые зоны»),
   * а не выезжающее окно: шапка задачи слева, ворклоги — широкой колонкой.
   */
  sheet?: boolean;
  /** Стрелки «предыдущая / следующая» для шапки панели. */
  nav?: ReactNode;
}

interface DrawerContentProps {
  issueId: string;
  issueKey: string;
  periodStart: string;
  periodEnd: string;
  onDrillDown: (id: string) => void;
  onSaved: () => void;
  sheet?: boolean;
}

function DrawerContent({ issueId, periodStart, periodEnd, onDrillDown, onSaved, sheet = false }: DrawerContentProps) {
  const { data: context, isLoading, isError, refetch } = useIssueContext(issueId);
  const { items: categories } = useCategories();
  // В скине период — по-русски («01.10.2026 – 31.10.2026»), в Aurora — как прежде.
  const ru = !!useSkin();

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

  const about = (
    <>
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
    </>
  );
  const worklogs = (
    <div
      className="an-drawer-worklogs"
      style={{
        background: 'var(--an-panel-bg, var(--faint-fill, rgba(255,255,255,0.03)))',
        border: '1px solid var(--an-panel-border, var(--hairline, rgba(255,255,255,0.08)))',
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
          color: 'var(--text-muted, #64748b)',
          padding: '10px 14px 8px',
          borderBottom: '1px solid var(--an-panel-line, var(--hairline, rgba(255,255,255,0.06)))',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span>Ворклоги за период</span>
        <span style={{ fontSize: 11, fontWeight: 500, letterSpacing: 0, textTransform: 'none', color: 'var(--text-muted, #64748b)' }}>
          {ru ? `${isoDateToRu(periodStart)} – ${isoDateToRu(periodEnd)}` : `${periodStart} – ${periodEnd}`}
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
  );

  // Панель: о задаче — слева, ворклоги с комментариями — широкой колонкой справа.
  if (sheet) {
    return (
      <div className="an-sheet-grid">
        <div className="an-sheet-side">{about}</div>
        <div className="an-sheet-main">{worklogs}</div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '16px 20px' }}>
      {about}
      {/* Worklogs section */}
      {worklogs}
    </div>
  );
}

/** Заголовок панели: ключ задачи ссылкой на Jira и название. */
function SheetTitle({ issueId, issueKey }: { issueId: string; issueKey: string }) {
  const { data: context } = useIssueContext(issueId);
  return (
    <>
      <JiraIssueLink issueKey={issueKey}>{issueKey}</JiraIssueLink>
      {context && <> · {context.summary}</>}
    </>
  );
}

/** Под заголовком: тип и статус задачи. */
function SheetSubtitle({ issueId }: { issueId: string }) {
  const { data: context } = useIssueContext(issueId);
  if (!context) return null;
  return (
    <>
      {context.issue_type}{' '}
      <Tag color={statusTagColor(context.status, context.status_category)} style={{ fontSize: 11 }}>
        {context.status}
      </Tag>
    </>
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
      className="an-drawer-head"
      style={{
        padding: '16px 20px 14px',
        borderBottom: '1px solid var(--an-panel-line-2, var(--hairline, rgba(255,255,255,0.1)))',
        background: 'var(--an-panel-head-bg, var(--bg, #0d1c33))',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        {canGoBack && (
          <Button
            size="small"
            type="text"
            onClick={onBack}
            style={{ color: 'var(--text-muted, #94a3b8)', padding: '0 6px', marginRight: 2 }}
          >
            ← назад
          </Button>
        )}
        <JiraIssueLink
          issueKey={issueKey}
          style={{
            fontFamily: 'monospace',
            fontSize: 13,
            fontWeight: 700,
            color: 'var(--an-key, #00c9c8)',
            background: 'var(--an-key-bg, rgba(0,201,200,0.08))',
            border: '1px solid var(--an-key-border, rgba(0,201,200,0.25))',
            borderRadius: 5,
            padding: '3px 8px',
            textDecoration: 'none',
            whiteSpace: 'nowrap',
          }}
        >
          {issueKey}
        </JiraIssueLink>
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
          role="button"
          aria-label="Закрыть"
          className="an-drawer-close"
          style={{
            marginLeft: 'auto',
            width: 28,
            height: 28,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 6,
            color: 'var(--text-muted, #64748b)',
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
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text, #e6edf7)', lineHeight: 1.4 }}>
          {context.summary}
        </div>
      ) : (
        <div style={{ fontSize: 13, color: 'var(--text-muted, #94a3b8)' }}>{issueKey}</div>
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
  sheet = false,
  nav,
}: Props) {
  // Back-stack: stack of {id, key} entries. Current is top of stack.
  const [stack, setStack] = useState<Array<{ id: string; key: string }>>([]);
  const qc = useQueryClient();

  // Смена задачи снаружи сбрасывает стек. Правим состояние прямо при отрисовке,
  // а не эффектом после неё — иначе панель рисуется дважды на каждое открытие.
  const [syncedId, setSyncedId] = useState<string | null>(null);
  if ((issueId ?? null) !== syncedId) {
    setSyncedId(issueId ?? null);
    setStack(issueId && issueKey ? [{ id: issueId, key: issueKey }] : []);
  }

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

  const body = currentEntry && (
    <>
      <DrawerHeader
        issueId={currentEntry.id}
        issueKey={currentEntry.key}
        canGoBack={stack.length > 1}
        onBack={handleBack}
        onClose={handleClose}
      />
      <div style={{ flex: 1, overflowY: 'auto', background: 'var(--an-panel-body-bg, var(--bg, #0f2340))' }}>
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
  );

  if (sheet) {
    if (!currentEntry) return null;
    return (
      <DetailSheet
        open
        onClose={handleClose}
        ariaLabel="Карточка задачи"
        className="an-issue-sheet"
        title={<SheetTitle issueId={currentEntry.id} issueKey={currentEntry.key} />}
        subtitle={<SheetSubtitle issueId={currentEntry.id} />}
        extra={(
          <>
            {stack.length > 1 && <Button onClick={handleBack}>← назад</Button>}
            {nav}
          </>
        )}
      >
        <DrawerContent
          key={currentEntry.id}
          issueId={currentEntry.id}
          issueKey={currentEntry.key}
          periodStart={periodStart}
          periodEnd={periodEnd}
          onDrillDown={handleDrillDown}
          onSaved={handleSaved}
          sheet
        />
      </DetailSheet>
    );
  }

  return (
    <Drawer
      open={open}
      onClose={handleClose}
      destroyOnClose={false}
      closable={false}
      styles={{
        header: { display: 'none' },
        body: { padding: 0, display: 'flex', flexDirection: 'column' },
        wrapper: { width: 720 },
      }}
    >
      {body}
    </Drawer>
  );
}
