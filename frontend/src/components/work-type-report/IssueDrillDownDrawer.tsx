import { useState } from 'react';
import {
  Alert,
  Button,
  Collapse,
  Drawer,
  Select,
  Skeleton,
  Tag,
  message,
} from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import { useIssueContext } from '../../hooks/useIssueContext';
import { useIssueWorklogs } from '../../hooks/useIssueWorklogs';
import { useThemeList } from '../../hooks/useThemeDictionary';
import { useManualClassify } from '../../hooks/useWorkTypeReport';
import { statusTagColor } from '../../utils/status';
import { DARK_THEME } from '../../utils/constants';

const JIRA_BASE = 'https://itgri.atlassian.net/browse';

const SECTION_LABEL_STYLE: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: DARK_THEME.textHint,
  marginBottom: 6,
};

const SECTION_STYLE: React.CSSProperties = {
  background: 'rgba(255,255,255,0.03)',
  border: `1px solid ${DARK_THEME.border}`,
  borderRadius: 6,
  padding: '10px 12px',
};

interface Props {
  open: boolean;
  issueId: string | null;
  issueKey: string | null;
  workTypeId: string;
  periodStart: string;
  periodEnd: string;
  onClose: () => void;
  /** Theme name from snapshot — may be null for unclassified issues */
  themeName?: string | null;
  /** Contribution text from snapshot */
  contribution?: string | null;
  /** Whether this issue is in manual_review_required list */
  needsManualClassify?: boolean;
}

// ---- Worklogs section ----

function WorklogsSection({ issueId, periodStart, periodEnd }: { issueId: string; periodStart: string; periodEnd: string }) {
  const { data: worklogs, isLoading, isError } = useIssueWorklogs(issueId, periodStart, periodEnd);

  if (isLoading) return <Skeleton active paragraph={{ rows: 2 }} />;
  if (isError) return <div style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>Не удалось загрузить ворклоги</div>;
  if (!worklogs || worklogs.length === 0) {
    return <div style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>Ворклогов за период нет</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {worklogs.map((w) => (
        <div
          key={w.worklog_id}
          style={{
            padding: '6px 8px',
            background: DARK_THEME.darkAccent,
            borderRadius: 4,
            fontSize: 12,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: w.comment ? 3 : 0 }}>
            <span style={{ color: DARK_THEME.textSecondary, fontWeight: 500 }}>{w.employee_name}</span>
            <span style={{ color: DARK_THEME.textMuted }}>
              {w.started_at.slice(0, 10)} · {w.hours.toFixed(1)} ч
            </span>
          </div>
          {w.comment && (
            <div style={{ color: DARK_THEME.textMuted, fontStyle: 'italic' }}>{w.comment}</div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---- Classification section ----

function ClassificationSection({
  issueId,
  workTypeId,
  themeName,
  contribution,
  needsManualClassify,
  onClose,
}: {
  issueId: string;
  workTypeId: string;
  themeName?: string | null;
  contribution?: string | null;
  needsManualClassify?: boolean;
  onClose: () => void;
}) {
  const [selectedThemeId, setSelectedThemeId] = useState<string | null>(null);
  const { data: themeList } = useThemeList(workTypeId, false);
  const classify = useManualClassify();

  const showDropdown = needsManualClassify || !themeName;

  const handleSave = () => {
    if (!selectedThemeId) {
      message.warning('Выберите тему');
      return;
    }
    classify.mutate(
      { issue_id: issueId, work_type_id: workTypeId, theme_id: selectedThemeId },
      { onSuccess: () => onClose() },
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {themeName && (
        <div>
          <div style={{ color: DARK_THEME.textSecondary, fontSize: 13 }}>
            Тема: <strong>{themeName}</strong>
          </div>
          {contribution && (
            <div style={{ color: DARK_THEME.textMuted, fontStyle: 'italic', fontSize: 12, marginTop: 3 }}>
              {contribution}
            </div>
          )}
        </div>
      )}

      {showDropdown && (
        <div>
          {!themeName && (
            <div style={{ color: DARK_THEME.amber, fontSize: 12, marginBottom: 8 }}>
              Классификация не определена — назначьте тему вручную
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Select
              placeholder="Выберите тему"
              style={{ flex: 1 }}
              value={selectedThemeId}
              onChange={setSelectedThemeId}
              options={(themeList?.themes ?? []).map((t) => ({
                value: t.id,
                label: t.name,
              }))}
              size="small"
            />
            <Button
              size="small"
              type="primary"
              loading={classify.isPending}
              onClick={handleSave}
            >
              Сохранить
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Main drawer content ----

function DrawerContent({
  issueId,
  issueKey,
  workTypeId,
  periodStart,
  periodEnd,
  themeName,
  contribution,
  needsManualClassify,
  onClose,
}: Omit<Props, 'open'> & { issueId: string; issueKey: string }) {
  const { data: context, isLoading, isError, refetch } = useIssueContext(issueId);

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

  const descriptionLong = (context.description?.length ?? 0) > 600;
  const goals = context.goals
    ? context.goals.split(',').map((g) => g.trim()).filter(Boolean)
    : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '16px 20px' }}>
      {/* Header: key + status + Jira link */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span
          style={{
            fontFamily: 'monospace',
            fontSize: 14,
            fontWeight: 700,
            color: DARK_THEME.cyanPrimary,
            background: 'rgba(0,201,200,0.08)',
            border: '1px solid rgba(0,201,200,0.25)',
            borderRadius: 5,
            padding: '3px 8px',
          }}
        >
          {issueKey}
        </span>
        <Tag
          color={statusTagColor(context.status, context.status_category)}
          style={{ marginInlineEnd: 0, fontSize: 11 }}
        >
          {context.status}
        </Tag>
        <Button
          type="link"
          size="small"
          icon={<LinkOutlined />}
          href={`${JIRA_BASE}/${issueKey}`}
          target="_blank"
          rel="noreferrer"
          style={{ padding: 0, color: DARK_THEME.textMuted, fontSize: 12 }}
        >
          Открыть в Jira
        </Button>
      </div>

      {/* Summary */}
      <div style={{ fontSize: 13, fontWeight: 500, color: DARK_THEME.textPrimary, lineHeight: 1.5 }}>
        {context.summary}
      </div>

      {/* Описание */}
      {context.description && (
        <div style={SECTION_STYLE}>
          <div style={SECTION_LABEL_STYLE}>Описание</div>
          {descriptionLong ? (
            <Collapse
              ghost
              size="small"
              items={[{
                key: 'desc',
                label: <span style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>Показать полностью</span>,
                children: (
                  <div style={{ color: DARK_THEME.textSecondary, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                    {context.description}
                  </div>
                ),
              }]}
            />
          ) : (
            <div style={{ color: DARK_THEME.textSecondary, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
              {context.description}
            </div>
          )}
        </div>
      )}

      {/* Цели */}
      {goals.length > 0 && (
        <div style={SECTION_STYLE}>
          <div style={SECTION_LABEL_STYLE}>Цели</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {goals.map((g) => (
              <Tag key={g} color="purple" style={{ marginInlineEnd: 0, fontSize: 12 }}>
                {g}
              </Tag>
            ))}
          </div>
        </div>
      )}

      {/* Ворклоги */}
      <div style={SECTION_STYLE}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 8,
          }}
        >
          <div style={SECTION_LABEL_STYLE}>Ворклоги за период</div>
          <span style={{ fontSize: 11, color: DARK_THEME.textHint }}>
            {periodStart} – {periodEnd}
          </span>
        </div>
        <WorklogsSection issueId={issueId} periodStart={periodStart} periodEnd={periodEnd} />
      </div>

      {/* Тематическая классификация */}
      <div style={SECTION_STYLE}>
        <div style={SECTION_LABEL_STYLE}>Тематическая классификация</div>
        <ClassificationSection
          issueId={issueId}
          workTypeId={workTypeId}
          themeName={themeName}
          contribution={contribution}
          needsManualClassify={needsManualClassify}
          onClose={onClose}
        />
      </div>
    </div>
  );
}

// ---- Exported drawer ----

export default function IssueDrillDownDrawer({
  open,
  issueId,
  issueKey,
  workTypeId,
  periodStart,
  periodEnd,
  onClose,
  themeName,
  contribution,
  needsManualClassify,
}: Props) {
  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      closable
      title={
        issueKey ? (
          <span style={{ fontFamily: 'monospace', color: DARK_THEME.cyanPrimary }}>{issueKey}</span>
        ) : (
          'Задача'
        )
      }
      styles={{
        body: { padding: 0, background: DARK_THEME.cardBg },
        header: { background: DARK_THEME.cardBg, borderBottom: `1px solid ${DARK_THEME.border}` },
        wrapper: { width: 600, background: DARK_THEME.cardBg },
      }}
    >
      {open && issueId && issueKey && (
        <div style={{ overflowY: 'auto', height: '100%', background: DARK_THEME.cardBg }}>
          <DrawerContent
            key={issueId}
            issueId={issueId}
            issueKey={issueKey}
            workTypeId={workTypeId}
            periodStart={periodStart}
            periodEnd={periodEnd}
            onClose={onClose}
            themeName={themeName}
            contribution={contribution}
            needsManualClassify={needsManualClassify}
          />
        </div>
      )}
    </Drawer>
  );
}
