import { Card, Tag, Typography } from 'antd';
import {
  FLAG_COLOR, FLAG_ICON, FLAG_LABELS, FLAG_ORDER, type FlagCode,
} from '../../api/teamDesk';
import { FLAG_TONE } from '../../utils/teamDeskView';

interface Props {
  flagCounts: Partial<Record<FlagCode, number>>;
  value: FlagCode | null;
  onChange: (flag: FlagCode | null) => void;
  /** Компактный вид скина: строка без своей карточки, пилюли без значков. */
  compact?: boolean;
}

/** Лента признаков-фильтров одной строкой. Общая для всех трёх раскладок. */
export function FlagFilterBar({ flagCounts, value, onChange, compact = false }: Props) {
  const empty = FLAG_ORDER.every((f) => !flagCounts[f]);
  if (compact) {
    return (
      <div className="tdc-bar" role="group" aria-label="Требует внимания">
        <span className="tdc-bar-label">Требует внимания</span>
        {FLAG_ORDER.filter((f) => flagCounts[f]).map((flag) => {
          const active = value === flag;
          return (
            <button
              key={flag}
              type="button"
              aria-pressed={active}
              className={`tdc-chip is-${FLAG_TONE[flag]}${active ? ' is-active' : ''}`}
              onClick={() => onChange(active ? null : flag)}
            >
              {FLAG_LABELS[flag]} <b>{flagCounts[flag]}</b>{active ? ' ✕' : ''}
            </button>
          );
        })}
        {empty && <span className="tdc-bar-empty">Замечаний нет</span>}
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
          ТРЕБУЕТ ВНИМАНИЯ
        </Typography.Text>
        {FLAG_ORDER.filter((f) => flagCounts[f]).map((flag) => {
          const active = value === flag;
          return (
            <Tag
              key={flag}
              color={active ? 'blue' : FLAG_COLOR[flag]}
              // Выбранный отбор виден без сравнения оттенков: жирная рамка,
              // жирный текст и крестик снятия.
              style={{
                cursor: 'pointer',
                marginInlineEnd: 0,
                fontWeight: active ? 700 : undefined,
                outline: active ? '2px solid #4ba3ff' : undefined,
              }}
              onClick={() => onChange(active ? null : flag)}
            >
              {FLAG_ICON[flag]} {FLAG_LABELS[flag]} · {flagCounts[flag]}{active ? ' ✕' : ''}
            </Tag>
          );
        })}
        {empty && <Typography.Text type="secondary">Замечаний нет</Typography.Text>}
      </div>
    </Card>
  );
}
