import { Tag, Tooltip } from 'antd';
import {
  STATUS_GROUP_COLOR, STATUS_GROUP_LABELS, statusGroupOf,
} from '../../api/teamDesk';

interface Props {
  /** Разбивка задач по статусам, как её отдал сервер. */
  counts: Record<string, number>;
  /** Какие статусы показывать и в каком порядке — решает вызывающая сторона. */
  statuses: string[];
  statusGroups?: Record<string, string[]>;
  /** Статус, по которому сейчас отфильтрован список задач. */
  selected?: string | null;
  onSelect?: (status: string | null) => void;
}

/**
 * Строка счётчиков статусов: точка группы + название + число.
 * Клик оставляет в списке задач только этот статус, повторный — снимает фильтр.
 */
export function StatusCounters({
  counts, statuses, statusGroups, selected = null, onSelect,
}: Props) {
  const shown = statuses.filter((status) => counts[status]);
  if (!shown.length) return null;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {shown.map((status) => {
        const group = statusGroupOf(statusGroups, status);
        const active = selected === status;
        return (
          <Tooltip key={status} title={`${status} · ${STATUS_GROUP_LABELS[group]}`}>
            <Tag
              onClick={
                onSelect
                  ? (e) => {
                      e.stopPropagation();
                      onSelect(active ? null : status);
                    }
                  : undefined
              }
              style={{
                marginInlineEnd: 0,
                cursor: onSelect ? 'pointer' : undefined,
                borderColor: active ? STATUS_GROUP_COLOR[group] : undefined,
                background: active ? 'rgba(75,163,255,0.14)' : undefined,
              }}
            >
              <span
                style={{
                  display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                  background: STATUS_GROUP_COLOR[group], marginRight: 6,
                }}
              />
              {status} <b>{counts[status]}</b>
            </Tag>
          </Tooltip>
        );
      })}
    </div>
  );
}
