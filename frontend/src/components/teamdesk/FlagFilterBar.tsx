import { Card, Tag, Typography } from 'antd';
import {
  FLAG_COLOR, FLAG_ICON, FLAG_LABELS, FLAG_ORDER, type FlagCode,
} from '../../api/teamDesk';

interface Props {
  flagCounts: Partial<Record<FlagCode, number>>;
  value: FlagCode | null;
  onChange: (flag: FlagCode | null) => void;
}

/** Лента признаков-фильтров одной строкой. Общая для всех трёх раскладок. */
export function FlagFilterBar({ flagCounts, value, onChange }: Props) {
  const empty = FLAG_ORDER.every((f) => !flagCounts[f]);
  return (
    <Card size="small" styles={{ body: { padding: '7px 12px' } }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 12, whiteSpace: 'nowrap' }}
        >
          ТРЕБУЕТ ВНИМАНИЯ
        </Typography.Text>
        {FLAG_ORDER.filter((f) => flagCounts[f]).map((flag) => (
          <Tag
            key={flag}
            color={value === flag ? 'blue' : FLAG_COLOR[flag]}
            style={{ cursor: 'pointer', marginInlineEnd: 0 }}
            onClick={() => onChange(value === flag ? null : flag)}
          >
            {FLAG_ICON[flag]} {FLAG_LABELS[flag]} · {flagCounts[flag]}
          </Tag>
        ))}
        {empty && <Typography.Text type="secondary">Замечаний нет</Typography.Text>}
      </div>
    </Card>
  );
}
