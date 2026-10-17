import { Card, Typography } from 'antd';
import { StatusCounters } from './StatusCounters';

interface Props {
  /** Задачи по статусам на весь срез — сумма по разработчикам. */
  counts: Record<string, number>;
  statuses: string[];
  statusGroups?: Record<string, string[]>;
  value: string | null;
  onChange: (status: string | null) => void;
  /** Компактный вид скина: строка без своей карточки, пилюли цвета группы. */
  compact?: boolean;
}

/** Лента статусов-фильтров одной строкой: клик оставляет в списке этот статус. */
export function StatusFilterBar({
  counts, statuses, statusGroups, value, onChange, compact = false,
}: Props) {
  const empty = !statuses.some((s) => counts[s]);
  if (compact) {
    return (
      <div className="tdc-bar" role="group" aria-label="Задачи по статусам">
        <span className="tdc-bar-label">Задачи по статусам</span>
        <StatusCounters
          compact="chip"
          counts={counts}
          statuses={statuses}
          statusGroups={statusGroups}
          selected={value}
          onSelect={onChange}
        />
        {empty && <span className="tdc-bar-empty">Задач нет</span>}
      </div>
    );
  }
  return (
    <Card size="small" styles={{ body: { padding: '7px 12px' } }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 12, whiteSpace: 'nowrap' }}
        >
          ЗАДАЧИ ПО СТАТУСАМ
        </Typography.Text>
        <StatusCounters
          counts={counts}
          statuses={statuses}
          statusGroups={statusGroups}
          selected={value}
          onSelect={onChange}
        />
        {empty && <Typography.Text type="secondary">Задач нет</Typography.Text>}
      </div>
    </Card>
  );
}
