import { Space, Tag, Typography } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtDate } from './format';
import type { UnloggedDaysData } from '../../types/desk';

export default function UnloggedDaysWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<UnloggedDaysData>(token, 'unlogged_days');
  const days = data?.days ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={days.length === 0}
      emptyText="Все дни заполнены"
    >
      <Space size={[8, 8]} wrap>
        {days.map((d) => (
          <Tag key={d.date} color="warning">
            {fmtDate(d.date)}
            <Typography.Text type="secondary"> · {d.expected_hours} ч</Typography.Text>
          </Tag>
        ))}
      </Space>
    </WidgetShell>
  );
}
