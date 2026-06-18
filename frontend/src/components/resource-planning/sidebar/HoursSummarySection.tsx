import { Col, Collapse, Row, Statistic, Typography } from 'antd';
import type { HoursSummary } from '../../../api/resourcePlanning';

interface Props {
  data: HoursSummary | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function HoursSummarySection({ data, collapsed, onToggleCollapse }: Props) {
  return (
    <Collapse
      ghost
      activeKey={collapsed ? [] : ['1']}
      onChange={onToggleCollapse}
      items={[{
        key: '1',
        label: 'Длительность vs часы',
        children: data == null
          ? <Typography.Text type="secondary">Нет данных</Typography.Text>
          : (
            <>
              <Row gutter={16} style={{ marginBottom: 8 }}>
                <Col span={6}>
                  <Statistic title="Всего ч" value={data.total} precision={1} />
                </Col>
                <Col span={6}>
                  <Statistic title="Использовано ч" value={data.used} precision={1} />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="Осталось ч"
                    value={data.remaining}
                    precision={1}
                    styles={data.remaining > 0 ? { content: { color: '#ef4444' } } : undefined}
                  />
                </Col>
                <Col span={6}>
                  <Statistic title="Рабочих дней" value={data.workdays} />
                </Col>
              </Row>
              {data.blocked_days > 0 && (
                <Typography.Text style={{ fontSize: 12, color: '#ffb432' }}>
                  Дней заблокировано: {data.blocked_days}
                </Typography.Text>
              )}
            </>
          ),
      }]}
    />
  );
}
