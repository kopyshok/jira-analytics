import type { EmployeeLoadOut } from '../../api/resourcePlanning';

interface Props {
  rows: EmployeeLoadOut[];
}

function colorFor(pct: number): string {
  if (pct <= 90) return 'rgba(34,197,94,0.45)';
  if (pct <= 110) return 'rgba(234,179,8,0.7)';
  return 'rgba(239,68,68,0.85)';
}

/**
 * Тепловая карта посуточной загрузки сотрудников плана.
 * Каждая строка — сотрудник, столбец — день квартала.
 * Зелёный ≤90%, жёлтый 90–110%, красный >110%.
 */
export default function EmployeeLoadHeatmap({ rows }: Props) {
  if (rows.length === 0) return null;
  return (
    <div
      style={{
        background: '#0a1628',
        border: '1px solid #1e3a5f',
        borderRadius: 8,
        padding: 12,
        marginBottom: 12,
      }}
    >
      <div style={{ fontSize: 12, color: '#8ab0d8', marginBottom: 8 }}>
        Загрузка сотрудников по дням квартала
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {rows.map((row) => (
          <div key={row.employee_id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div
              style={{
                width: 160,
                fontSize: 12,
                color: '#fff',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {row.employee_name ?? row.employee_id}
            </div>
            <div style={{ flex: 1, display: 'flex', height: 8 }}>
              {row.days.map((d) => (
                <div
                  key={d.date}
                  title={`${d.date}: ${d.pct.toFixed(0)}%`}
                  style={{ flex: 1, background: colorFor(d.pct) }}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
