import { Collapse, Table, Typography } from 'antd';
import type { DailyBreakdownItem } from '../../../api/resourcePlanning';

interface Props {
  items: DailyBreakdownItem[];
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const STATUS_LABELS: Record<DailyBreakdownItem['status'], string> = {
  work: 'Работа',
  absence: 'Отсутствие',
  holiday: 'Праздник',
  weekend: 'Выходной',
  blocked_by_other: 'Занят другой задачей',
};

function formatDateDDMM(dateStr: string): string {
  const d = new Date(dateStr);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}`;
}

export default function DailyBreakdownSection({ items, collapsed, onToggleCollapse }: Props) {
  return (
    <Collapse
      ghost
      activeKey={collapsed ? [] : ['1']}
      onChange={onToggleCollapse}
      items={[{
        key: '1',
        label: 'Дни × часы',
        children: items.length === 0
          ? <Typography.Text type="secondary">Нет данных</Typography.Text>
          : (
            <Table<DailyBreakdownItem>
              size="small"
              pagination={false}
              dataSource={items}
              rowKey="date"
              onRow={(row) => ({
                style: row.status === 'blocked_by_other'
                  ? { background: 'rgba(239,68,68,0.08)' }
                  : row.status !== 'work'
                    ? { background: 'rgba(255,180,50,0.06)' }
                    : {},
              })}
              columns={[
                {
                  title: 'Дата',
                  dataIndex: 'date',
                  width: 60,
                  render: formatDateDDMM,
                },
                {
                  title: 'Доступно ч',
                  dataIndex: 'available_hours',
                  width: 80,
                  render: (v: number) => v.toFixed(1),
                },
                {
                  title: 'Потрачено ч',
                  dataIndex: 'used_hours',
                  width: 90,
                  render: (v: number) => v.toFixed(1),
                },
                {
                  title: 'Статус',
                  dataIndex: 'status',
                  width: 140,
                  render: (v: DailyBreakdownItem['status']) => STATUS_LABELS[v] ?? v,
                },
                {
                  title: 'Источник',
                  key: 'source',
                  render: (_: unknown, row: DailyBreakdownItem) =>
                    row.status === 'blocked_by_other'
                      ? `${row.blocker_item_key ?? ''} · ${row.blocker_phase_label ?? ''}`.replace(/^ · | · $/, '')
                      : '',
                },
              ]}
            />
          ),
      }]}
    />
  );
}
