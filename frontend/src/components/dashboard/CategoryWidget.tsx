import { Card, Spin, Empty } from 'antd';
import type { DashboardCategoriesResponse, CategoryMetaItem } from '../../types/api';
import { formatHours } from '../../utils/format';

function Treemap({ items, totalHours }: { items: CategoryMetaItem[]; totalHours: number }) {
  if (!items.length) return <Empty description="Нет данных" />;

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, width: '100%', minHeight: 160 }}>
      {items.map((item) => {
        const pct = totalHours > 0 ? item.hours / totalHours : 0;
        const minW = pct > 0.15 ? 120 : pct > 0.07 ? 80 : 60;
        return (
          <div
            key={item.key}
            title={`${item.label}: ${formatHours(item.hours)} ч (${item.pct.toFixed(1)}%)`}
            style={{
              flex: `${pct * 100} 0 ${minW}px`,
              minHeight: 56,
              background: `${item.color}33`,
              border: `1.5px solid ${item.color}66`,
              borderRadius: 8,
              padding: '8px 10px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              overflow: 'hidden',
            }}
          >
            <div style={{ fontSize: 11, color: '#a4b8d8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {item.label}
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#fff' }}>{formatHours(item.hours)} ч</div>
            {pct > 0.07 && (
              <div style={{ fontSize: 10, color: '#7e94b8' }}>{item.pct.toFixed(0)}%</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function MetaTable({ items }: { items: CategoryMetaItem[] }) {
  const totalHours = items.reduce((s, i) => s + i.hours, 0);
  const totalWl = items.reduce((s, i) => s + i.worklog_count, 0);
  const totalIssues = items.reduce((s, i) => s + i.issue_count, 0);

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ color: '#7e94b8', fontSize: 10, textTransform: 'uppercase' }}>
            {['Категория', 'Часы', 'Вркл.', 'Задач', 'Сотр.', 'Ср.мин', '%'].map((h) => (
              <th key={h} style={{ textAlign: h === 'Категория' ? 'left' : 'right', padding: '4px 8px', borderBottom: '1px solid #1c3358' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.key} style={{ borderBottom: '1px solid rgba(28,51,88,.3)' }}>
              <td style={{ padding: '5px 8px' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: item.color, flexShrink: 0, display: 'inline-block' }} />
                  <span style={{ color: '#e6edf7' }}>{item.label}</span>
                </span>
              </td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#fff', fontWeight: 600 }}>{formatHours(item.hours)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.worklog_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.issue_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.employee_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.avg_worklog_minutes.toFixed(0)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#7e94b8' }}>{item.pct.toFixed(1)}%</td>
            </tr>
          ))}
          <tr style={{ borderTop: '2px solid #1c3358', fontWeight: 600, color: '#fff', fontSize: 11 }}>
            <td style={{ padding: '5px 8px' }}>Итого</td>
            <td style={{ textAlign: 'right', padding: '5px 8px' }}>{formatHours(totalHours)}</td>
            <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{totalWl}</td>
            <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{totalIssues}</td>
            <td colSpan={3} />
          </tr>
        </tbody>
      </table>
    </div>
  );
}

interface Props {
  data: DashboardCategoriesResponse | undefined;
  loading: boolean;
}

export default function CategoryWidget({ data, loading }: Props) {
  if (loading) return <Card title="Ворклоги по категориям"><Spin /></Card>;
  if (!data?.items.length) return <Card title="Ворклоги по категориям"><Empty description="Нет данных" /></Card>;

  return (
    <Card title="Ворклоги по категориям задач">
      <div style={{ display: 'grid', gridTemplateColumns: '55% 45%', gap: 16 }}>
        <Treemap items={data.items} totalHours={data.total_hours} />
        <MetaTable items={data.items} />
      </div>
    </Card>
  );
}
