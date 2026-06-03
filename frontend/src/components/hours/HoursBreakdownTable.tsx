import { Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import { DARK_THEME } from '../../utils/constants';
import type { HoursBreakdownData } from '../../api/issues';

const ROLES: Array<{ key: 'analyst' | 'dev' | 'qa' | 'opo'; label: string }> = [
  { key: 'analyst', label: 'Аналитик' },
  { key: 'dev', label: 'Разработка' },
  { key: 'qa', label: 'Тестирование' },
  { key: 'opo', label: 'ОПЭ' },
];

const COLOR = {
  past: '#94a3b8',
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
    },
  ];

  const columns: ColumnsType<Row> = [
    { title: 'Роль', dataIndex: 'role', width: 130 },
    { title: 'План', dataIndex: 'plan', align: 'right', render: fmt },
    {
      title: 'Факт прошлых Q',
      dataIndex: 'fact_past',
      align: 'right',
      render: (v: number) => <span style={{ color: COLOR.past }}>{fmt(v)}</span>,
    },
    {
      title: 'Факт текущий',
      dataIndex: 'fact_current',
      align: 'right',
      render: (v: number) => <span style={{ color: COLOR.current }}>{fmt(v)}</span>,
    },
    {
      title: 'Утверждено',
      dataIndex: 'approved',
      align: 'right',
      render: (v: number) => <span style={{ color: COLOR.approved }}>{fmt(v)}</span>,
    },
    {
      title: 'Запланировать',
      dataIndex: 'planable',
      align: 'right',
      render: (v: number) => (
        <span
          style={{
            color: v < 0 ? DARK_THEME.danger : COLOR.planable,
            fontWeight: 600,
          }}
        >
          {fmt(v)}
        </span>
      ),
    },
    {
      title: 'Черновик',
      dataIndex: 'draft',
      align: 'right',
      render: (v: number) => <span style={{ color: COLOR.draft }}>{fmt(v)}</span>,
    },
  ];

  return (
    <div>
      <ProgressBar data={data} />
      <Table<Row>
        size="small"
        loading={loading}
        pagination={false}
        rowKey="key"
        dataSource={rows}
        columns={columns}
      />
      <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {data.flags.overrun && <Tag color="error">Перерасход</Tag>}
        {data.flags.plan_missing && <Tag color="warning">План не задан</Tag>}
        {data.flags.draft_exceeds_planable && <Tag color="warning">Черновики превышают остаток</Tag>}
      </div>
    </div>
  );
}
