import { Tag } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtRelative } from './format';
import { statusTagColor } from '../../utils/status';
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
      <div className="desk-await-hint">
        Задачи, где вы исполнитель и последним ответил кто-то другой.
      </div>
      {items.map((it, i) => {
        const jiraUrl = it.key ? `https://itgri.atlassian.net/browse/${it.key}` : null;
        const label = `${it.key ? `${it.key} · ` : ''}${it.title ?? '—'}`;
        return (
          <div className="desk-await-item" key={`${it.key ?? ''}-${i}`}>
            <div className="desk-await-title">
              {jiraUrl ? <a href={jiraUrl} target="_blank" rel="noreferrer">{label}</a> : label}
            </div>
            <div className="desk-await-sub">
              {it.status && <Tag color={statusTagColor(it.status, null)}>{it.status}</Tag>}
              <span>
                последний комментарий: {it.last_comment_author ?? '—'}
                {it.last_comment_at ? `, ${fmtRelative(it.last_comment_at)}` : ''}
              </span>
            </div>
          </div>
        );
      })}
    </WidgetShell>
  );
}
