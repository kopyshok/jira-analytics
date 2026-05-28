import { Space, Table, Tag } from 'antd';
import { useQuery } from '@tanstack/react-query';
import {
  usageApi,
  type UsageActionRow,
  type UsageActionTopUser,
} from '../../../api/usage';

interface Props {
  days: number;
}

export default function UsageActionsTable({ days }: Props) {
  const { data = [], isLoading } = useQuery({
    queryKey: ['usage', 'actions', days] as const,
    queryFn: () => usageApi.actions(days),
  });

  const columns = [
    { title: 'Действие', dataIndex: 'action_type', key: 'action_type' },
    {
      title: 'Всего',
      dataIndex: 'total',
      key: 'total',
      sorter: (a: UsageActionRow, b: UsageActionRow) => a.total - b.total,
      defaultSortOrder: 'descend' as const,
    },
    {
      title: 'Топ-3 пользователя',
      dataIndex: 'top_users',
      key: 'top_users',
      render: (users: UsageActionTopUser[]) => (
        <Space wrap size={4}>
          {users.map((u) => (
            <Tag key={u.user_id}>
              {u.display_name} ({u.count})
            </Tag>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <Table<UsageActionRow>
      rowKey="action_type"
      loading={isLoading}
      dataSource={data}
      columns={columns}
      pagination={false}
      size="small"
    />
  );
}
