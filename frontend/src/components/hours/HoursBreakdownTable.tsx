import { Tag, Tooltip } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { HoursBreakdownData } from '../../api/issues';

const ROLES: Array<{ key: 'analyst' | 'dev' | 'qa' | 'opo'; label: string }> = [
  { key: 'analyst', label: 'Аналитик' },
  { key: 'dev', label: 'Разработка' },
  { key: 'qa', label: 'Тестирование' },
  { key: 'opo', label: 'ОПЭ' },
];

const COLOR = {
  past: 'var(--text-muted, #94a3b8)',
  current: '#fb923c',
  approved: '#38bdf8',
  planable: '#22c55e',
  draft: '#a78bfa',
};

interface Row {
  key: string;
  role: string;
  plan: number;
  fact_past: number;
  fact_current: number;
  approved: number;
  planable: number;
  draft: number;
  isTotal?: boolean;
}

interface Props {
  data: HoursBreakdownData;
  loading?: boolean;
}

function fmt(v: number): string {
  return v === 0 ? '—' : String(Math.round(v));
}

function ProgressBar({ data }: { data: HoursBreakdownData }) {
  const total = data.plan.total || 1;
  const pct = (v: number) => `${(Math.max(0, v) / total) * 100}%`;
  const past = data.fact_past.total;
  const current = data.fact_current.total;
  const approvedRemaining = Math.max(0, data.approved.total - data.fact_current.total);
  const planable = Math.max(0, data.planable.total);

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', height: 18, borderRadius: 3, overflow: 'hidden', background: '#1e293b' }}>
        <Tooltip title={`Факт прошлых Q: ${Math.round(past)}ч`}>
          <div style={{ background: COLOR.past, width: pct(past) }} />
        </Tooltip>
        <Tooltip title={`Факт текущий: ${Math.round(current)}ч`}>
          <div style={{ background: COLOR.current, width: pct(current) }} />
        </Tooltip>
        <Tooltip title={`Утверждено (остаток): ${Math.round(approvedRemaining)}ч`}>
          <div style={{ background: COLOR.approved, width: pct(approvedRemaining) }} />
        </Tooltip>
        <Tooltip title={`Запланировать: ${Math.round(planable)}ч`}>
          <div style={{ background: COLOR.planable, width: pct(planable) }} />
        </Tooltip>
      </div>
      <div style={{ fontSize: 11, color: COLOR.draft, marginTop: 6 }}>
        Черновик: {Math.round(data.draft.total)}ч (информационно)
      </div>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: '6px 8px',
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-muted, #94a3b8)',
  borderBottom: '1px solid #1e3a5f',
  textAlign: 'right',
  whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  padding: '6px 8px',
  fontSize: 13,
  borderBottom: '1px solid rgba(255,255,255,0.04)',
  textAlign: 'right',
};

export default function HoursBreakdownTable({ data, loading }: Props) {
  const rows: Row[] = [
    ...ROLES.map(({ key, label }) => ({
      key,
      role: label,
      plan: data.plan[key] ?? 0,
      fact_past: data.fact_past[key] ?? 0,
      fact_current: data.fact_current[key] ?? 0,
      approved: data.approved[key] ?? 0,
      planable: data.planable[key] ?? 0,
      draft: data.draft[key] ?? 0,
    })),
    {
      key: 'total',
      role: 'Итого',
      plan: data.plan.total ?? 0,
      fact_past: data.fact_past.total ?? 0,
      fact_current: data.fact_current.total ?? 0,
      approved: data.approved.total ?? 0,
      planable: data.planable.total ?? 0,
      draft: data.draft.total ?? 0,
      isTotal: true,
    },
  ];

  return (
    <div style={{ opacity: loading ? 0.5 : 1 }}>
      <ProgressBar data={data} />
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={{ ...thStyle, textAlign: 'left', width: 130 }}>Роль</th>
            <th style={thStyle}>План</th>
            <th style={thStyle}>Факт прошлых Q</th>
            <th style={thStyle}>Факт текущий</th>
            <th style={thStyle}>Утверждено</th>
            <th style={thStyle}>Запланировать</th>
            <th style={thStyle}>Черновик</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const baseTd = r.isTotal ? { ...tdStyle, fontWeight: 600 } : tdStyle;
            return (
              <tr key={r.key}>
                <td style={{ ...baseTd, textAlign: 'left' }}>{r.role}</td>
                <td style={baseTd}>{fmt(r.plan)}</td>
                <td style={{ ...baseTd, color: COLOR.past }}>{fmt(r.fact_past)}</td>
                <td style={{ ...baseTd, color: COLOR.current }}>{fmt(r.fact_current)}</td>
                <td style={{ ...baseTd, color: COLOR.approved }}>{fmt(r.approved)}</td>
                <td
                  style={{
                    ...baseTd,
                    color: r.planable < 0 ? DARK_THEME.danger : COLOR.planable,
                    fontWeight: 600,
                  }}
                >
                  {fmt(r.planable)}
                </td>
                <td style={{ ...baseTd, color: COLOR.draft }}>{fmt(r.draft)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {data.flags.overrun && <Tag color="error">Перерасход</Tag>}
        {data.flags.plan_missing && <Tag color="warning">План не задан</Tag>}
        {data.flags.draft_exceeds_planable && <Tag color="warning">Черновики превышают остаток</Tag>}
      </div>
    </div>
  );
}
