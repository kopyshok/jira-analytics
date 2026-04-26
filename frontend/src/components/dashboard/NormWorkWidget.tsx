import { Card, Spin, Empty, Tooltip } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import type { DashboardNormWorkResponse, NormWorkItem } from '../../types/api';
import { formatHours } from '../../utils/format';

const DEFAULT_THRESHOLDS = { warnAbove: 110, underBelow: 70 };

function barColor(pct: number): string {
  if (pct > DEFAULT_THRESHOLDS.warnAbove) return '#ff4d4f';
  if (pct < DEFAULT_THRESHOLDS.underBelow) return '#faad14';
  return '#52c41a';
}

function BulletBar({ item }: { item: NormWorkItem }) {
  const color = barColor(item.pct);
  // target line at 66% of track width (leaves 34% room for overrun)
  const targetPct = 66;
  const fillWidth = item.plan_hours > 0
    ? Math.min(100, (item.fact_hours / item.plan_hours) * targetPct)
    : 0;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '160px 1fr 90px',
        alignItems: 'center',
        gap: 12,
        padding: '8px 0',
        borderBottom: '1px solid rgba(28,51,88,.4)',
      }}
    >
      <div style={{ fontSize: 12, color: '#e6edf7', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {item.label}
      </div>
      <div style={{ position: 'relative', height: 16, background: '#1c3358', borderRadius: 4, overflow: 'visible' }}>
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            height: '100%',
            width: `${fillWidth}%`,
            background: color,
            borderRadius: 4,
            transition: 'width .3s',
          }}
        />
        {/* target line */}
        <div
          style={{
            position: 'absolute',
            top: -3,
            bottom: -3,
            left: `${targetPct}%`,
            width: 2,
            background: '#fff',
            borderRadius: 1,
          }}
        />
      </div>
      <div style={{ textAlign: 'right', fontSize: 12 }}>
        <span style={{ color, fontWeight: 600 }}>{item.pct.toFixed(0)}%</span>
        <div style={{ color: '#7e94b8', fontSize: 10 }}>
          {formatHours(item.fact_hours)}/{formatHours(item.plan_hours)} ч
        </div>
      </div>
    </div>
  );
}

interface Props {
  data: DashboardNormWorkResponse | undefined;
  loading: boolean;
}

export default function NormWorkWidget({ data, loading }: Props) {
  const extra = (
    <Tooltip title="Настройка порогов">
      <SettingOutlined style={{ cursor: 'pointer', color: '#7e94b8' }} />
    </Tooltip>
  );

  if (loading) return <Card title="Нормированные работы" extra={extra}><Spin /></Card>;
  if (!data?.items.length) return <Card title="Нормированные работы" extra={extra}><Empty description="Нет данных" /></Card>;

  return (
    <Card title="Нормированные работы: план / факт" extra={extra}>
      {data.items.map((item) => (
        <BulletBar key={item.work_type_id} item={item} />
      ))}
      <div
        style={{
          display: 'flex',
          gap: 24,
          marginTop: 12,
          paddingTop: 10,
          borderTop: '1px solid #1c3358',
          fontSize: 12,
          color: '#7e94b8',
        }}
      >
        <span>
          Σ план: <b style={{ color: '#fff' }}>{formatHours(data.total_plan)} ч</b>
        </span>
        <span>
          Σ факт: <b style={{ color: '#fff' }}>{formatHours(data.total_fact)} ч</b>
        </span>
        <span>
          Загрузка: <b style={{ color: barColor(data.total_pct) }}>{data.total_pct.toFixed(0)}%</b>
        </span>
      </div>
    </Card>
  );
}
