import { Button, Tag, Typography } from 'antd';
import { FLAG_ICON, FLAG_LABELS, type FlagCode } from '../../api/teamDesk';
import { QUEUE_SCOPE_LABEL, type QueueScope } from './queueFilter';

interface Props {
  developerName?: string | null;
  flag: FlagCode | null;
  status: string | null;
  queueScope: QueueScope;
  onReset: () => void;
}

/**
 * Что именно сейчас отобрано — одной строкой над таблицей задач.
 * Без неё через минуту анализа непонятно, почему список короткий.
 */
export function ActiveFilters({
  developerName, flag, status, queueScope, onReset,
}: Props) {
  const chips: { key: string; node: React.ReactNode }[] = [];
  if (developerName) chips.push({ key: developerName, node: developerName });
  if (queueScope) chips.push({ key: queueScope, node: QUEUE_SCOPE_LABEL[queueScope] });
  if (flag) {
    chips.push({
      key: flag,
      node: <><span className="desk-flag-icon">{FLAG_ICON[flag]} </span>{FLAG_LABELS[flag]}</>,
    });
  }
  if (status) chips.push({ key: `status:${status}`, node: status });
  if (!chips.length) return null;

  return (
    <div className="desk-active" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <Typography.Text type="secondary" className="desk-bar-label" style={{ fontSize: 12 }}>ОТОБРАНО</Typography.Text>
      {chips.map((chip) => (
        <Tag key={chip.key} color="blue" style={{ marginInlineEnd: 0, fontWeight: 600 }}>
          {chip.node}
        </Tag>
      ))}
      <Button size="small" type="link" onClick={onReset}>Сбросить</Button>
    </div>
  );
}
