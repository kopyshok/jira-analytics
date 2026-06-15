import { List, Tag, Typography } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtDate, fmtRange } from './format';
import type { TeamAvailabilityData } from '../../types/desk';

export default function TeamAvailabilityWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<TeamAvailabilityData>(
    token,
    'team_availability',
  );
  const members = data?.members ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={members.length === 0}
      emptyText="Нет занятости на этой неделе"
    >
      {data?.week_start && (
        <Typography.Text type="secondary">
          Неделя с {fmtDate(data.week_start)}
        </Typography.Text>
      )}
      <List
        size="small"
        dataSource={members}
        renderItem={(m) => (
          <List.Item>
            <List.Item.Meta
              title={m.name}
              description={m.busy.map((b, i) => (
                <div key={i}>
                  <Tag>{fmtRange(b.start, b.end)}</Tag>
                  {b.label ?? ''}
                </div>
              ))}
            />
          </List.Item>
        )}
      />
    </WidgetShell>
  );
}
