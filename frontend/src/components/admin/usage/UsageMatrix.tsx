import { useMemo } from 'react';
import { Empty, Table, Tooltip } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { usageApi } from '../../../api/usage';
import { pathLabel } from './pathLabels';

interface Props {
  days: number;
}

interface MatrixRow {
  user_id: string;
  display_name: string;
}

export default function UsageMatrix({ days }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['usage', 'matrix', days] as const,
    queryFn: () => usageApi.matrix(days),
    staleTime: 5 * 60_000,
  });

  const max = useMemo(() => {
    if (!data) return 0;
    return data.cells.reduce((m, c) => Math.max(m, c.hours), 0);
  }, [data]);

  const cellMap = useMemo(() => {
    const m = new Map<string, number>();
    if (data) for (const c of data.cells) m.set(`${c.user_id}|${c.path}`, c.hours);
    return m;
  }, [data]);

  if (!isLoading && (!data || data.users.length === 0)) {
    return <Empty description="Нет данных за период" />;
  }

  const tint = (h: number): React.CSSProperties | undefined => {
    if (h === 0 || max === 0) return undefined;
    const alpha = Math.min(1, h / max);
    return { background: `rgba(0, 201, 200, ${alpha.toFixed(2)})` };
  };

  const columns = [
    {
      title: 'Пользователь',
      dataIndex: 'display_name',
      key: 'display_name',
      fixed: 'left' as const,
      width: 180,
    },
    ...(data?.paths ?? []).map((p) => ({
      title: pathLabel(p.path),
      key: p.path,
      align: 'right' as const,
      width: 120,
      render: (_: unknown, row: MatrixRow) => {
        const h = cellMap.get(`${row.user_id}|${p.path}`) ?? 0;
        return (
          <Tooltip title={`${h.toFixed(1)} ч`}>
            <div style={{ ...tint(h), padding: '4px 8px', textAlign: 'right' }}>
              {h > 0 ? h.toFixed(1) : ''}
            </div>
          </Tooltip>
        );
      },
    })),
  ];

  return (
    <Table<MatrixRow>
      rowKey="user_id"
      loading={isLoading}
      dataSource={data?.users ?? []}
      columns={columns}
      pagination={false}
      scroll={{ x: 'max-content' }}
      size="small"
    />
  );
}
