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

  // Key-aware раскладка: «прочие» виджеты в обычной сетке, затем строка
  // «Переработка + Производственный календарь», затем «Отсутствия команды» во всю ширину внизу.
  const hasAbsences = widgets.includes('team_absences');
  // Пара «Переработка + Производственный календарь» рядом — только когда включены оба.
  const pairBothEnabled =
    widgets.includes('hours_balance') && widgets.includes('production_calendar');
  const pairKeys = pairBothEnabled ? ['hours_balance', 'production_calendar'] : [];
  // Прочие виджеты сохраняют порядок enabled_widgets; пара (если оба) и отсутствия вынесены.
  const others = widgets.filter(
    (k) => k !== 'team_absences' && !pairKeys.includes(k),
  );

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
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {others.length > 0 && (
            <Row gutter={[16, 16]}>
              {others.map((key) => {
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

          {pairKeys.length > 0 && (
            <Row gutter={[16, 16]}>
              {pairKeys.map((key) => {
                const def = WIDGET_REGISTRY[key];
                const W = def.component;
                return (
                  <Col key={key} xs={24} lg={12}>
                    <W token={token} title={def.title} />
                  </Col>
                );
              })}
            </Row>
          )}

          {hasAbsences && (
            <Row gutter={[16, 16]}>
              <Col xs={24} span={24}>
                {(() => {
                  const def = WIDGET_REGISTRY['team_absences'];
                  const W = def.component;
                  return <W token={token} title={def.title} />;
                })()}
              </Col>
            </Row>
          )}
        </Space>
      )}
    </div>
  );
}
