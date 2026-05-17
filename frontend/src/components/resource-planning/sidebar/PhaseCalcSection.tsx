import { Collapse, Descriptions, Typography } from 'antd';
import type { PhaseCalcDetails } from '../../../api/resourcePlanning';

interface Props {
  data: PhaseCalcDetails | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function PhaseCalcSection({ data, collapsed, onToggleCollapse }: Props) {
  return (
    <Collapse
      ghost
      activeKey={collapsed ? [] : ['1']}
      onChange={onToggleCollapse}
      items={[{
        key: '1',
        label: 'Часы по источникам',
        children: data == null
          ? <Typography.Text type="secondary">Нет данных</Typography.Text>
          : (
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="Длительность по Jira">
                {data.duration_days_jira != null ? `${data.duration_days_jira} д.` : 'не задано'}
              </Descriptions.Item>
              <Descriptions.Item label="Вовлечённость">
                {data.involvement_pct != null ? `${data.involvement_pct}%` : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="Параллельных исполнителей">
                {data.parallel_count}
              </Descriptions.Item>
              <Descriptions.Item label="Дневная ёмкость">
                {data.daily_capacity_hours.toFixed(1)} ч/день
              </Descriptions.Item>
            </Descriptions>
          ),
      }]}
    />
  );
}
