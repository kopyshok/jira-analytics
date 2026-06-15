import { List, Tag, Typography } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtRelative } from './format';
import { statusTagColor } from '../../utils/status';
import { DARK_THEME } from '../../utils/constants';
import type { AwaitingReactionData } from '../../types/desk';

export default function AwaitingReactionWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<AwaitingReactionData>(token, 'awaiting_reaction');
  const items = data?.items ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={items.length === 0}
      emptyText="Ничего не ждёт ответа"
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        Задачи, где вы исполнитель и последним ответил кто-то другой.
      </Typography.Paragraph>
      <List
        size="small"
        dataSource={items}
        renderItem={(it) => {
          const jiraUrl = it.key ? `https://example.atlassian.net/browse/${it.key}` : null;
          return (
            <List.Item>
              <List.Item.Meta
                title={
                  jiraUrl ? (
                    <Typography.Link href={jiraUrl} target="_blank" rel="noreferrer">
                      {it.key ? `${it.key} · ` : ''}{it.title ?? '—'}
                    </Typography.Link>
                  ) : (
                    <span>{it.title ?? it.key ?? '—'}</span>
                  )
                }
                description={
                  <span style={{ color: DARK_THEME.textMuted }}>
                    {it.status && <Tag color={statusTagColor(it.status, null)}>{it.status}</Tag>}
                    последний комментарий: {it.last_comment_author ?? '—'}
                    {it.last_comment_at ? `, ${fmtRelative(it.last_comment_at)}` : ''}
                  </span>
                }
              />
            </List.Item>
          );
        }}
      />
    </WidgetShell>
  );
}
