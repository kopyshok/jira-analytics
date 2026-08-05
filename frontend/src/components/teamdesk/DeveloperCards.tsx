import { Card, Col, Row, Tag, Tooltip, Typography } from 'antd';
import {
  FLAG_LABELS, FLAG_ORDER,
  type DeskDeveloper, type DeskWorkload, type FlagCode,
} from '../../api/teamDesk';
import { HoursScale } from './HoursScale';

const ICON: Record<FlagCode, string> = {
  over: '↑', under: '↓', decomp: '⊞', childgap: '⊟',
  noest: '∅', nospent: '◔', stale: '⏳',
};
const COLOR: Record<FlagCode, string> = {
  over: 'red', under: 'gold', decomp: 'orange', childgap: 'volcano',
  noest: 'default', nospent: 'default', stale: 'purple',
};

function initials(name: string | null): string {
  if (!name) return '?';
  const parts = name.split(' ');
  return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase();
}

function accuracyColor(value: number | null): string | undefined {
  if (value == null) return undefined;
  if (value > 1.3) return '#ff6b6b';
  if (value < 0.7) return '#eeb13c';
  return '#3ebd85';
}

interface Props {
  developers: DeskDeveloper[];
  workload: Record<string, DeskWorkload>;
  overrunPct: number;
  selected: string | null;
  onSelect: (id: string | null) => void;
}

/** Раскладка «Светофор»: карточка на разработчика, клик фильтрует таблицу. */
export function DeveloperCards({ developers, workload, overrunPct, selected, onSelect }: Props) {
  return (
    <Row gutter={[10, 10]}>
      {developers.map((dev) => {
        const severity = dev.flag_counts.over ? 2 : (dev.flag_counts.decomp || dev.flag_counts.stale) ? 1 : 0;
        const load = workload[dev.developer_id];
        const isSelected = selected === dev.developer_id;
        return (
          <Col key={dev.developer_id} xs={24} sm={12} lg={8} xxl={6}>
            <Card
              size="small"
              hoverable
              onClick={() => onSelect(isSelected ? null : dev.developer_id)}
              styles={{ body: { padding: 12 } }}
              style={{
                borderLeft: `3px solid ${severity === 2 ? '#ff6b6b' : severity === 1 ? '#eeb13c' : 'transparent'}`,
                outline: isSelected ? '2px solid #4ba3ff' : undefined,
              }}
            >
              <div style={{ display: 'flex', gap: 9, alignItems: 'center', marginBottom: 8 }}>
                <div
                  style={{
                    width: 30, height: 30, borderRadius: '50%',
                    display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 600,
                    background: 'rgba(125,145,170,0.18)',
                  }}
                >
                  {initials(dev.display_name)}
                </div>
                <div>
                  <Typography.Text strong>{dev.display_name ?? 'Без имени'}</Typography.Text>
                  {dev.team && (
                    <div style={{ fontSize: 11, opacity: 0.55 }}>{dev.team}</div>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 24, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                  {dev.total_issues}
                </span>
                <Typography.Text type="secondary" style={{ fontSize: 11.5 }}>
                  задач всего<br />
                  <b>{dev.in_dev}</b> у него · <b>{dev.waiting}</b> ждут не его · <b>{dev.todo}</b> не начаты
                </Typography.Text>
              </div>

              <HoursScale fact={dev.fact_hours} est={dev.est_hours || null} overrunPct={overrunPct} />

              <div style={{ display: 'flex', justifyContent: 'space-between', margin: '8px 0', fontSize: 11.5 }}>
                <Typography.Text type="secondary">точность оценок</Typography.Text>
                <span style={{ color: accuracyColor(dev.accuracy) }}>
                  {dev.accuracy == null ? '—' : `×${dev.accuracy.toFixed(2)}`}
                </span>
              </div>

              {load && (
                <div style={{ fontSize: 11.5, marginBottom: 8 }}>
                  <Typography.Text type="secondary">
                    очередь {load.queue_hours} ч
                    {load.queue_days != null ? ` ≈ ${load.queue_days} дн` : ' · нет свободных дней'}
                    {load.without_estimate > 0 ? ` · ещё ${load.without_estimate} без оценки` : ''}
                  </Typography.Text>
                </div>
              )}

              <div>
                {FLAG_ORDER.filter((f) => dev.flag_counts[f]).map((flag) => (
                  <Tooltip key={flag} title={FLAG_LABELS[flag]}>
                    <Tag color={COLOR[flag]}>{ICON[flag]} {dev.flag_counts[flag]}</Tag>
                  </Tooltip>
                ))}
                {FLAG_ORDER.every((f) => !dev.flag_counts[f]) && (
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>без замечаний</Typography.Text>
                )}
              </div>
            </Card>
          </Col>
        );
      })}
    </Row>
  );
}
