import { Card, Col, Row, Statistic } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { usageApi } from '../../../api/usage';

export default function UsageKpiBar() {
  const { data, isLoading } = useQuery({
    queryKey: ['usage', 'overview'] as const,
    queryFn: () => usageApi.overview(),
    staleTime: 5 * 60_000,
  });

  return (
    <Row gutter={16}>
      <Col xs={12} sm={12} lg={6}>
        <Card loading={isLoading}>
          <Statistic title="Активных сегодня" value={data?.dau ?? 0} />
        </Card>
      </Col>
      <Col xs={12} sm={12} lg={6}>
        <Card loading={isLoading}>
          <Statistic title="За неделю" value={data?.wau ?? 0} />
        </Card>
      </Col>
      <Col xs={12} sm={12} lg={6}>
        <Card loading={isLoading}>
          <Statistic title="За 30 дней" value={data?.mau ?? 0} />
        </Card>
      </Col>
      <Col xs={12} sm={12} lg={6}>
        <Card loading={isLoading}>
          <Statistic
            title="Часов за 30 дней"
            value={data?.hours_30d ?? 0}
            precision={1}
          />
        </Card>
      </Col>
    </Row>
  );
}
