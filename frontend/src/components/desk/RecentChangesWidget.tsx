import { List } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtRange } from './format';
import type { RecentChangesData } from '../../types/desk';

export default function RecentChangesWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<RecentChangesData>(token, 'recent_changes');
  const changes = data?.changes ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={changes.length === 0}
      emptyText="Изменений нет"
    >
      <List
        size="small"
        dataSource={changes}
        renderItem={(c) => (
          <List.Item>
            <List.Item.Meta
              title={
                <span>
                  {c.key ? `${c.key} · ` : ''}
                  {c.title ?? '—'}
                </span>
              }
              description={
                <span>
                  {c.change ?? ''} · {fmtRange(c.start_date, c.end_date)}
                </span>
              }
            />
          </List.Item>
        )}
      />
    </WidgetShell>
  );
}
