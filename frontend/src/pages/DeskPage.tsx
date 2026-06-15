import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { Avatar, Col, Result, Row, Space, Spin, Tag, Typography } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import { fetchDeskMeta } from '../api/desk';
import { DARK_THEME } from '../utils/constants';
import { WIDGET_REGISTRY } from '../components/desk/registry';

const ROMAN: Record<number, string> = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV' };

function periodLabel(year: number, quarter: number): string {
  return `${ROMAN[quarter] ?? quarter} квартал ${year}`;
}

export default function DeskPage() {
  const { token = '' } = useParams<{ token: string }>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['desk', token],
    queryFn: ({ signal }) => fetchDeskMeta(token, signal),
    retry: false,
    refetchInterval: 5 * 60_000,
  });

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
        <Result
          status="404"
          title="Рабочий стол не найден"
          subTitle="Рабочий стол не найден или ссылка отозвана."
        />
      </div>
    );
  }

  const { employee, teams, enabled_widgets, period } = data;
  const widgets = enabled_widgets.filter((k) => WIDGET_REGISTRY[k]);

  return (
    <div
      style={{
        minHeight: '100vh',
        background: DARK_THEME.pageBg,
        color: DARK_THEME.textPrimary,
        padding: '24px clamp(16px, 4vw, 48px)',
      }}
    >
      <Space align="center" size={16} style={{ marginBottom: 24 }} wrap>
        <Avatar size={56} src={employee.avatar_url ?? undefined} icon={<UserOutlined />} />
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {employee.display_name}
          </Typography.Title>
          <Space size={[8, 4]} wrap style={{ marginTop: 4 }}>
            {teams.map((t) => (
              <Tag key={t} color="cyan">
                {t}
              </Tag>
            ))}
            <Typography.Text type="secondary">{periodLabel(period.year, period.quarter)}</Typography.Text>
          </Space>
        </div>
      </Space>

      {widgets.length === 0 ? (
        <Typography.Text type="secondary">Виджеты не настроены.</Typography.Text>
      ) : (
        <Row gutter={[16, 16]}>
          {widgets.map((key) => {
            const def = WIDGET_REGISTRY[key];
            const W = def.component;
            return (
              <Col
                key={key}
                xs={24}
                sm={24}
                lg={def.wide ? 24 : 12}
                xl={def.wide ? 12 : 8}
              >
                <W token={token} title={def.title} />
              </Col>
            );
          })}
        </Row>
      )}
    </div>
  );
}
