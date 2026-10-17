import { Button, Tag, Typography } from 'antd';
import { FLAG_ICON, FLAG_LABELS, type FlagCode } from '../../api/teamDesk';
import { QUEUE_SCOPE_LABEL, type QueueScope } from './queueFilter';

interface Props {
  developerName?: string | null;
  flag: FlagCode | null;
  status: string | null;
  queueScope: QueueScope;
  onReset: () => void;
  /** Компактный вид скина: подпись обычным регистром, пилюли без значков. */
  compact?: boolean;
}

/**
 * Что именно сейчас отобрано — одной строкой над таблицей задач.
 * Без неё через минуту анализа непонятно, почему список короткий.
 */
export function ActiveFilters({
  developerName, flag, status, queueScope, onReset, compact = false,
}: Props) {
  const chips: string[] = [];
  if (developerName) chips.push(developerName);
  if (queueScope) chips.push(QUEUE_SCOPE_LABEL[queueScope]);
  if (flag) chips.push(compact ? FLAG_LABELS[flag] : `${FLAG_ICON[flag]} ${FLAG_LABELS[flag]}`);
  if (status) chips.push(status);
  if (!chips.length) return null;

  if (compact) {
    return (
      <div className="tdc-bar">
        <span className="tdc-bar-label">Отобрано</span>
        {chips.map((chip) => (
          <span key={chip} className="wr-pill is-accent">{chip}</span>
        ))}
        <button type="button" className="wr-link" onClick={onReset}>Сбросить</button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>ОТОБРАНО</Typography.Text>
      {chips.map((chip) => (
        <Tag key={chip} color="blue" style={{ marginInlineEnd: 0, fontWeight: 600 }}>
          {chip}
        </Tag>
      ))}
      <Button size="small" type="link" onClick={onReset}>Сбросить</Button>
    </div>
  );
}
