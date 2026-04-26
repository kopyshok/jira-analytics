import { Card, Row, Col, Tag, Spin, Empty } from 'antd';
import { useNavigate } from 'react-router';
import { PieChart, Pie, Cell, Tooltip } from 'recharts';
import type { DashboardProjectsResponse } from '../../types/api';
import { formatHours } from '../../utils/format';
import { CHART_COLORS } from '../../utils/constants';

const STATUS_COLORS = {
  done: CHART_COLORS.green,
  in_progress: '#00c9c8',
  overdue: CHART_COLORS.red,
  not_started: '#1c3358',
};

interface Props {
  data: DashboardProjectsResponse | undefined;
  loading: boolean;
}

export default function ProjectsWidget({ data, loading }: Props) {
  const navigate = useNavigate();

  if (loading) return <Card title="Проекты квартала"><Spin /></Card>;
  if (!data) return <Card title="Проекты квартала"><Empty description="Нет данных" /></Card>;

  const donutData = [
    { name: 'Завершено', value: data.done, color: STATUS_COLORS.done },
    { name: 'В работе', value: data.in_progress, color: STATUS_COLORS.in_progress },
    { name: 'Просрочено', value: data.overdue, color: STATUS_COLORS.overdue },
    { name: 'Не начаты', value: data.not_started, color: STATUS_COLORS.not_started },
  ].filter((d) => d.value > 0);

  const statusRows = [
    { label: 'Завершено', value: data.done, color: STATUS_COLORS.done },
    { label: 'В работе', value: data.in_progress, color: STATUS_COLORS.in_progress },
    { label: 'Просрочено', value: data.overdue, color: STATUS_COLORS.overdue },
    { label: 'Не начаты', value: data.not_started, color: '#7e94b8' },
  ];

  return (
    <Card title="Проекты квартала" style={{ height: '100%' }}>
      <Row gutter={16} align="middle" style={{ marginBottom: 16 }}>
        <Col flex="160px">
          <div style={{ position: 'relative', width: 160, height: 160 }}>
            <PieChart width={160} height={160}>
              <Pie
                data={donutData}
                cx={75}
                cy={75}
                innerRadius={50}
                outerRadius={72}
                dataKey="value"
                startAngle={90}
                endAngle={-270}
              >
                {donutData.map((e, i) => (
                  <Cell key={i} fill={e.color} />
                ))}
              </Pie>
              <Tooltip formatter={(v, name) => [`${v}`, name]} />
            </PieChart>
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                textAlign: 'center',
                pointerEvents: 'none',
              }}
            >
              <div style={{ fontSize: 24, fontWeight: 700, color: '#fff' }}>{data.total}</div>
              <div style={{ fontSize: 11, color: '#7e94b8' }}>проектов</div>
            </div>
          </div>
        </Col>
        <Col flex="1">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {statusRows.map((row) => (
              <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: row.color, flexShrink: 0, display: 'inline-block' }} />
                <span style={{ color: '#fff', fontWeight: 600, width: 28 }}>{row.value}</span>
                <span style={{ color: '#7e94b8' }}>
                  {row.label} ({data.total ? Math.round((row.value / data.total) * 100) : 0}%)
                </span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, fontSize: 12, color: '#7e94b8', borderTop: '1px solid #1c3358', paddingTop: 10 }}>
            Прогноз к концу квартала:{' '}
            <span style={{ color: '#00c9c8', fontWeight: 600 }}>
              {data.forecast_done} ({data.forecast_pct}%)
            </span>
          </div>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <div style={{ fontSize: 11, color: '#7e94b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            ⚠️ Требует внимания
          </div>
          {data.attention_list.length === 0 && (
            <div style={{ fontSize: 12, color: '#5a7099' }}>Всё в порядке</div>
          )}
          {data.attention_list.slice(0, 5).map((item) => (
            <div
              key={item.issue_key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '5px 0',
                borderBottom: '1px solid rgba(28,51,88,.4)',
                cursor: 'pointer',
                fontSize: 12,
              }}
              onClick={() => navigate(`/analytics?project=${item.issue_key}`)}
            >
              {item.days_overdue != null ? (
                <Tag color="red" style={{ fontSize: 10, margin: 0 }}>просрочен {item.days_overdue}д</Tag>
              ) : item.days_silent != null ? (
                <Tag color="orange" style={{ fontSize: 10, margin: 0 }}>тишина {item.days_silent}д</Tag>
              ) : null}
              <span style={{ color: '#fff', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.title}
              </span>
              <span style={{ color: '#7e94b8', flexShrink: 0 }}>{formatHours(item.fact_hours)} ч</span>
            </div>
          ))}
        </Col>
        <Col span={12}>
          <div style={{ fontSize: 11, color: '#7e94b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            🔴 Перебор по часам
          </div>
          {data.overrun_list.length === 0 && (
            <div style={{ fontSize: 12, color: '#5a7099' }}>Перерасхода нет</div>
          )}
          {data.overrun_list.slice(0, 5).map((item) => (
            <div
              key={item.issue_key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '5px 0',
                borderBottom: '1px solid rgba(28,51,88,.4)',
                fontSize: 12,
              }}
            >
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{ color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.title}
                </div>
                <div style={{ height: 4, borderRadius: 2, background: '#1c3358', marginTop: 3, overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      background: 'linear-gradient(90deg,#faad14,#ff4d4f)',
                      width: `${Math.min(100, (item.fact_hours / Math.max(item.plan_hours, 1)) * 100)}%`,
                    }}
                  />
                </div>
              </div>
              <span style={{ color: '#ff4d4f', fontWeight: 600, flexShrink: 0 }}>
                +{formatHours(item.delta_hours)} ч
              </span>
            </div>
          ))}
        </Col>
      </Row>
    </Card>
  );
}
