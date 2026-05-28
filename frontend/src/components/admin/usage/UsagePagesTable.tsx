import { Table } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { usageApi, type UsagePageRow } from '../../../api/usage';
import { pathLabel } from './pathLabels';

interface Props {
  days: number;
}

export default function UsagePagesTable({ days }: Props) {
  const { data = [], isLoading } = useQuery({
    queryKey: ['usage', 'pages', days] as const,
    queryFn: () => usageApi.pages(days),
  });

  const columns = [
    {
      title: 'Раздел',
      dataIndex: 'path',
      key: 'path',
      render: (p: string) => pathLabel(p),
    },
    {
      title: 'Уник. пользователей',
      dataIndex: 'unique_users',
      key: 'unique_users',
      sorter: (a: UsagePageRow, b: UsagePageRow) => a.unique_users - b.unique_users,
    },
    {
      title: 'Заходов',
      dataIndex: 'views',
      key: 'views',
      sorter: (a: UsagePageRow, b: UsagePageRow) => a.views - b.views,
    },
    {
      title: 'Часов',
      dataIndex: 'hours',
      key: 'hours',
      render: (h: number) => h.toFixed(1),
      sorter: (a: UsagePageRow, b: UsagePageRow) => a.hours - b.hours,
      defaultSortOrder: 'descend' as const,
    },
  ];

  return (
    <Table<UsagePageRow>
      rowKey="path"
      loading={isLoading}
      dataSource={data}
      columns={columns}
      pagination={false}
      size="small"
    />
  );
}
