import { Tooltip, Typography } from 'antd';
import { roundHours, type DeskDeveloper, type DeskWorkload } from '../../api/teamDesk';

interface Props {
  developers: DeskDeveloper[];
  workload: Record<string, DeskWorkload>;
  limit: number;
}

/** Сколько задач у человека одновременно в работе, с отсечкой лимита. */
export function WorkloadBars({ developers, workload, limit }: Props) {
  const max = Math.max(limit + 2, ...developers.map((d) => d.in_progress));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      {developers.map((dev) => {
        const load = workload[dev.developer_id];
        const over = dev.in_progress > limit;
        return (
          <div
            key={dev.developer_id}
            style={{ display: 'grid', gridTemplateColumns: '150px 1fr 30px', gap: 8, alignItems: 'center' }}
          >
            <Typography.Text type="secondary" ellipsis style={{ fontSize: 12 }}>
              {dev.display_name}
            </Typography.Text>
            <Tooltip
              title={
                load
                  ? `Очередь ${roundHours(load.queue_hours)} ч, свободно ${roundHours(load.available_hours)} ч на неделю`
                  : undefined
              }
            >
              <div style={{ position: 'relative', height: 14, background: 'rgba(125,145,170,0.22)', borderRadius: 3 }}>
                <div
                  style={{
                    position: 'absolute', left: 0, top: 0, bottom: 0,
                    width: `${(dev.in_progress / max) * 100}%`,
                    background: over ? '#ff6b6b' : '#4ba3ff',
                    borderRadius: 3, opacity: 0.85,
                  }}
                />
                <div
                  style={{
                    position: 'absolute', top: -2, bottom: -2,
                    left: `${(limit / max) * 100}%`,
                    borderLeft: '1px dashed rgba(160,175,195,0.8)',
                  }}
                />
              </div>
            </Tooltip>
            <span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{dev.in_progress}</span>
          </div>
        );
      })}
      <Typography.Text type="secondary" style={{ fontSize: 11.5 }}>
        пунктир — лимит {limit} задач
      </Typography.Text>
    </div>
  );
}
