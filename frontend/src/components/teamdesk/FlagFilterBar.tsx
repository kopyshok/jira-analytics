import { Card, Space, Tag, Typography } from 'antd';
import {
  FLAG_COLOR, FLAG_ICON, FLAG_LABELS, FLAG_ORDER, type FlagCode,
} from '../../api/teamDesk';

interface Props {
  flagCounts: Partial<Record<FlagCode, number>>;
  value: FlagCode | null;
  onChange: (flag: FlagCode | null) => void;
}

/** Лента признаков-фильтров. Общая для всех трёх раскладок. */
export function FlagFilterBar({ flagCounts, value, onChange }: Props) {
  const empty = FLAG_ORDER.every((f) => !flagCounts[f]);
  return (
    <Card size="small" title="Что требует внимания">
      <Space wrap size={6}>
        {FLAG_ORDER.filter((f) => flagCounts[f]).map((flag) => (
          <Tag
            key={flag}
            color={value === flag ? 'blue' : FLAG_COLOR[flag]}
            style={{ cursor: 'pointer' }}
            onClick={() => onChange(value === flag ? null : flag)}
          >
            {FLAG_ICON[flag]} {FLAG_LABELS[flag]} · {flagCounts[flag]}
          </Tag>
        ))}
        {empty && <Typography.Text type="secondary">Замечаний нет</Typography.Text>}
      </Space>
    </Card>
  );
}
