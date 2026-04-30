import { Card, Spin, Empty } from 'antd';
import type { DashboardCategoriesResponse, CategoryMetaItem } from '../../types/api';

function HeatmapGrid({ items }: { items: CategoryMetaItem[] }) {
  if (!items.length) return <Empty description="Нет данных" />;

  const visible = items.slice(0, 10);
  const overflow = items.length > 10 ? items.slice(10) : [];

  const cells: (CategoryMetaItem | { _overflow: true; count: number; hours: number })[] = [...visible];
  if (overflow.length) {
    cells.push({
      _overflow: true,
      count: overflow.length,
      hours: overflow.reduce((s, i) => s + i.hours, 0),
    });
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gridAutoRows: 'minmax(140px, 1fr)',
        gap: 6,
        width: '100%',
      }}
    >
      {cells.map((c, idx) => {
        if ('_overflow' in c) {
          return (
            <div
              key={`overflow-${idx}`}
              style={{
                background: '#1c335833',
                border: '1px solid #1c335866',
                borderRadius: 8,
                padding: 12,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ fontSize: 12, color: '#a4b8d8' }}>+ ещё {c.count}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#fff' }}>{Math.round(c.hours)} ч</div>
            </div>
          );
        }
        const item = c;
        return (
          <div
            key={item.key}
            title={`${item.label}: ${Math.round(item.hours)} ч (${item.pct.toFixed(1)}%)`}
            style={{
              background: `${item.color}33`,
              border: `1px solid ${item.color}66`,
              borderRadius: 8,
              padding: 12,
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              overflow: 'hidden',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
              <div style={{
                fontSize: 12,
                color: '#a4b8d8',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
              }}>
                {item.label}
              </div>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                background: item.color,
                color: '#fff',
                padding: '2px 6px',
                borderRadius: 6,
                flexShrink: 0,
              }}>
                {item.pct.toFixed(0)}%
              </span>
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#fff' }}>{Math.round(item.hours)} ч</div>
            <div style={{ fontSize: 10, color: '#7e94b8' }}>
              {item.worklog_count} wl · {item.issue_count} зад · {item.employee_count} чел
            </div>
            <div style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              height: 3,
              width: `${Math.min(100, item.pct)}%`,
              background: item.color,
            }} />
          </div>
        );
      })}
    </div>
  );
}

function SummaryStrip({ items }: { items: CategoryMetaItem[] }) {
  const totalHours = items.reduce((s, i) => s + i.hours, 0);
  const totalWl = items.reduce((s, i) => s + i.worklog_count, 0);
  const totalIssues = items.reduce((s, i) => s + i.issue_count, 0);
  const avgMin = totalWl > 0
    ? items.reduce((s, i) => s + i.avg_worklog_minutes * i.worklog_count, 0) / totalWl
    : 0;
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: 16,
      marginTop: 12,
      fontSize: 12,
      color: '#7e94b8',
    }}>
      <span>Σ часов: <b style={{ color: '#fff' }}>{Math.round(totalHours)}</b></span>
      <span>Σ ворклогов: <b style={{ color: '#fff' }}>{totalWl}</b></span>
      <span>Σ задач: <b style={{ color: '#fff' }}>{totalIssues}</b></span>
      <span>{items.length} категорий</span>
      <span>средн. <b style={{ color: '#fff' }}>{avgMin.toFixed(0)}</b> мин/wl</span>
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
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#fff', fontWeight: 600 }}>{Math.round(item.hours)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.worklog_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.issue_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.employee_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#a4b8d8' }}>{item.avg_worklog_minutes.toFixed(0)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: '#7e94b8' }}>{item.pct.toFixed(1)}%</td>
            </tr>
          ))}
          <tr style={{ borderTop: '2px solid #1c3358', fontWeight: 600, color: '#fff', fontSize: 11 }}>
            <td style={{ padding: '5px 8px' }}>Итого</td>
            <td style={{ textAlign: 'right', padding: '5px 8px' }}>{Math.round(totalHours)}</td>
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
      <div style={{ display: 'grid', gridTemplateColumns: '60% 40%', gap: 16 }}>
        <div>
          <HeatmapGrid items={data.items} />
          <SummaryStrip items={data.items} />
        </div>
        <MetaTable items={data.items} />
      </div>
    </Card>
  );
}
