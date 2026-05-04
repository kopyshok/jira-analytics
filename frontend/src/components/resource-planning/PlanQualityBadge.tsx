import { Tag, Tooltip, Skeleton } from 'antd';
import { usePlanQuality } from '../../hooks/useResourcePlanningV2';

interface Props {
  planId: string | null;
}

export default function PlanQualityBadge({ planId }: Props) {
  const { data, isLoading } = usePlanQuality(planId);
  if (!planId) return null;
  if (isLoading) return <Skeleton.Button active size="small" style={{ width: 240 }} />;
  if (!data) return null;
  const overloadColor = data.overload_days_pct > 20 ? 'red' : data.overload_days_pct > 5 ? 'orange' : 'green';
  const lateColor = data.late_count > 0 ? 'red' : 'green';
  return (
    <Tooltip title="Качество расписания: % перегруженных дней · число просрочек · среднее использование ёмкости">
      <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
        <Tag color={overloadColor}>Перегрузки: {data.overload_days_pct}%</Tag>
        <Tag color={lateColor}>Просрочки: {data.late_count}</Tag>
        <Tag color="blue">Утилизация: {data.mean_utilization_pct}%</Tag>
      </span>
    </Tooltip>
  );
}
