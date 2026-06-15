import { List, Tag, Typography } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtRange } from './format';
import type { MyConflictsData } from '../../types/desk';

export default function MyConflictsWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<MyConflictsData>(token, 'my_conflicts');
  const conflicts = data?.conflicts ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={conflicts.length === 0}
      emptyText="Конфликтов нет"
    >
      <List
        size="small"
        dataSource={conflicts}
        renderItem={(c) => (
          <List.Item>
            <List.Item.Meta
              title={
                <span>
                  <Tag color="error">{c.type}</Tag>
                  {c.metric_value != null && (
                    <Typography.Text type="secondary">{c.metric_value}</Typography.Text>
                  )}
                </span>
              }
              description={
                <span>
                  {fmtRange(c.window_start, c.window_end)}
                  {c.message ? ` · ${c.message}` : ''}
                </span>
              }
            />
          </List.Item>
        )}
      />
    </WidgetShell>
  );
}
