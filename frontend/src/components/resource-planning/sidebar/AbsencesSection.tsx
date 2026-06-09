import { Collapse, Tag, Typography } from 'antd';
import type { AbsenceWindowItem } from '../../../api/resourcePlanning';

interface Props {
  items: AbsenceWindowItem[];
  collapsed: boolean;
  onToggleCollapse: () => void;
}

function formatRange(item: AbsenceWindowItem): string {
  if (item.date_start === item.date_end) {
    const d = new Date(item.date_start);
    return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
  }
  const s = new Date(item.date_start);
  const e = new Date(item.date_end);
  const fmt = (d: Date) => `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
  return `${fmt(s)}-${fmt(e)}`;
}

export default function AbsencesSection({ items, collapsed, onToggleCollapse }: Props) {
  return (
    <Collapse
      ghost
      activeKey={collapsed ? [] : ['1']}
      onChange={onToggleCollapse}
      items={[{
        key: '1',
        label: 'Отсутствия в окне',
        children: items.length === 0
          ? <Typography.Text type="secondary">Нет данных</Typography.Text>
          : (
            <div>
              {items.map((item, idx) => (
                <div
                  key={`${item.date_start}-${item.date_end}-${idx}`}
                  style={{ padding: '4px 0', display: 'flex', alignItems: 'center' }}
                >
                  <span style={{ fontSize: 12, color: 'var(--text-2, #cfe1f5)' }}>
                    {formatRange(item)} — {item.reason_label}
                  </span>
                  <Tag
                    color={item.is_holiday ? 'orange' : 'default'}
                    style={{ marginLeft: 8, fontSize: 11 }}
                  >
                    {item.is_holiday ? 'Праздник РФ' : 'Отсутствие'}
                  </Tag>
                </div>
              ))}
            </div>
          ),
      }]}
    />
  );
}
