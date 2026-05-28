import { Card, Empty } from 'antd';
import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { usageApi } from '../../../api/usage';

interface Props {
  days: number;
}

export default function UsageTimeline({ days }: Props) {
  const { data = [], isLoading } = useQuery({
    queryKey: ['usage', 'timeline', days] as const,
    queryFn: () => usageApi.timeline(days),
    staleTime: 5 * 60_000,
  });

  if (!isLoading && data.length === 0) {
    return <Empty description="Нет данных за период" />;
  }

  return (
    <Card loading={isLoading} title="Динамика">
      <div style={{ height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line
              type="monotone"
              dataKey="views"
              name="Заходов"
              stroke="#00c9c8"
            />
            <Line
              type="monotone"
              dataKey="active_users"
              name="Активных пользователей"
              stroke="#52c41a"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
