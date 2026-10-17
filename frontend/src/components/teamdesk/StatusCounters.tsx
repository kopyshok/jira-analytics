import { Tag, Tooltip } from 'antd';
import {
  STATUS_GROUP_COLOR, STATUS_GROUP_LABELS, statusGroupOf,
} from '../../api/teamDesk';
import { STATUS_GROUP_TONE } from '../../utils/teamDeskView';

interface Props {
  /** Разбивка задач по статусам, как её отдал сервер. */
  counts: Record<string, number>;
  /** Какие статусы показывать и в каком порядке — решает вызывающая сторона. */
  statuses: string[];
  statusGroups?: Record<string, string[]>;
  /** Статус, по которому сейчас отфильтрован список задач. */
  selected?: string | null;
  onSelect?: (status: string | null) => void;
  /**
   * Компактный вид скина: мягкие пилюли цвета группы статуса вместо меток с
   * точкой; `chip` — крупные пилюли-кнопки полосы отборов.
   */
  compact?: 'pill' | 'chip';
}

/**
 * Строка счётчиков статусов: точка группы + название + число.
 * Клик оставляет в списке задач только этот статус, повторный — снимает фильтр.
 */
export function StatusCounters({
  counts, statuses, statusGroups, selected = null, onSelect, compact,
}: Props) {
  const shown = statuses.filter((status) => counts[status]);
  if (!shown.length) return null;
  if (compact) {
    return (
      <>
        {shown.map((status) => {
          const group = statusGroupOf(statusGroups, status);
          const active = selected === status;
          const tone = STATUS_GROUP_TONE[group];
          const cls = compact === 'chip'
            ? `tdc-chip is-${tone}${active ? ' is-active' : ''}`
            : `wr-pill is-sm is-${tone} tdc-pill${active ? ' is-active' : ''}${onSelect ? ' is-click' : ''}`;
          const label = compact === 'chip'
            ? <>{status} <b>{counts[status]}</b></>
            : <>{status} {counts[status]}</>;
          return (
            <Tooltip key={status} title={`${status} · ${STATUS_GROUP_LABELS[group]}`}>
              {onSelect ? (
                <button
                  type="button"
                  className={cls}
                  aria-pressed={active}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(active ? null : status);
                  }}
                >
                  {label}{active ? ' ✕' : ''}
                </button>
              ) : (
                <span className={cls}>{label}</span>
              )}
            </Tooltip>
          );
        })}
      </>
    );
  }
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
              // Выбранный статус видно сразу: жирная рамка и текст, крестик
              // снятия. Одного оттенка фона для этого мало.
              style={{
                marginInlineEnd: 0,
                cursor: onSelect ? 'pointer' : undefined,
                borderColor: active ? '#4ba3ff' : undefined,
                outline: active ? '2px solid #4ba3ff' : undefined,
                fontWeight: active ? 700 : undefined,
                background: active ? 'rgba(75,163,255,0.22)' : undefined,
              }}
            >
              <span
                style={{
                  display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                  background: STATUS_GROUP_COLOR[group], marginRight: 6,
                }}
              />
              {status} <b>{counts[status]}</b>{active ? ' ✕' : ''}
            </Tag>
          </Tooltip>
        );
      })}
    </div>
  );
}
