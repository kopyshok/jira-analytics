import { Table, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { usageApi, type UsageUserRow } from '../../../api/usage';
import { pathLabel } from './pathLabels';

interface Props {
  days: number;
}

export default function UsageUsersTable({ days }: Props) {
  const { data = [], isLoading } = useQuery({
    queryKey: ['usage', 'users', days] as const,
    queryFn: () => usageApi.users(days),
  });

  const columns = [
    { title: 'Пользователь', dataIndex: 'display_name', key: 'display_name' },
    {
      title: 'Роль',
      dataIndex: 'role',
      key: 'role',
      render: (r: string) => <Tag>{r}</Tag>,
    },
    {
      title: 'Последний вход',
      dataIndex: 'last_seen',
      key: 'last_seen',
      render: (d: string | null) =>
        d ? new Date(d).toLocaleDateString('ru-RU') : '—',
      sorter: (a: UsageUserRow, b: UsageUserRow) =>
        (a.last_seen ?? '').localeCompare(b.last_seen ?? ''),
    },
    {
      title: 'Активных дней',
      dataIndex: 'active_days',
      key: 'active_days',
      sorter: (a: UsageUserRow, b: UsageUserRow) => a.active_days - b.active_days,
    },
    {
      title: 'Часов',
      dataIndex: 'hours',
      key: 'hours',
      render: (h: number) => h.toFixed(1),
      sorter: (a: UsageUserRow, b: UsageUserRow) => a.hours - b.hours,
      defaultSortOrder: 'descend' as const,
    },
    {
      title: 'Самый частый раздел',
      dataIndex: 'top_path',
      key: 'top_path',
      render: (p: string | null) => (p ? pathLabel(p) : '—'),
    },
  ];

  return (
    <Table<UsageUserRow>
      rowKey="user_id"
      loading={isLoading}
      dataSource={data}
      columns={columns}
      pagination={{ pageSize: 20 }}
      size="small"
    />
  );
}
