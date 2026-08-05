import { Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  FLAG_LABELS, FLAG_ORDER,
  type DeskDeveloper, type DeskWorkload, type FlagCode,
} from '../../api/teamDesk';
import { HoursScale } from './HoursScale';

const ICON: Record<FlagCode, string> = {
  over: '↑', under: '↓', decomp: '⊞', childgap: '⊟',
  noest: '∅', nospent: '◔', stale: '⏳',
};
const COLOR: Record<FlagCode, string> = {
  over: 'red', under: 'gold', decomp: 'orange', childgap: 'volcano',
  noest: 'default', nospent: 'default', stale: 'purple',
};

interface Props {
  developers: DeskDeveloper[];
  workload: Record<string, DeskWorkload>;
  overrunPct: number;
  selected: string | null;
  onSelect: (id: string | null) => void;
}

/** Раскладка «Ведомость»: строка на разработчика, снизу итог. */
export function DeveloperTable({ developers, workload, overrunPct, selected, onSelect }: Props) {
  const columns: ColumnsType<DeskDeveloper> = [
    {
      title: 'Разработчик',
      dataIndex: 'display_name',
      ellipsis: true,
      sorter: (a, b) => (a.display_name ?? '').localeCompare(b.display_name ?? ''),
      render: (v: string | null, row) => (
        <>
          <Typography.Text strong>{v ?? 'Без имени'}</Typography.Text>
          {row.team && (
            <div style={{ fontSize: 11, opacity: 0.55 }}>{row.team}</div>
          )}
        </>
      ),
    },
    { title: 'Задач', dataIndex: 'total_issues', width: 72, align: 'right',
      sorter: (a, b) => a.total_issues - b.total_issues },
    { title: 'У него', dataIndex: 'in_dev', width: 76, align: 'right',
      sorter: (a, b) => a.in_dev - b.in_dev },
    { title: 'Ждут не его', dataIndex: 'waiting', width: 104, align: 'right',
      sorter: (a, b) => a.waiting - b.waiting },
    { title: 'Не начаты', dataIndex: 'todo', width: 92, align: 'right',
      sorter: (a, b) => a.todo - b.todo },
    {
      title: 'Факт / оценка',
      width: 170,
      render: (_, row) => (
        <HoursScale fact={row.fact_hours} est={row.est_hours || null} overrunPct={overrunPct} width={150} />
      ),
    },
    {
      title: 'Точность',
      dataIndex: 'accuracy',
      width: 84,
      align: 'right',
      sorter: (a, b) => (a.accuracy ?? 0) - (b.accuracy ?? 0),
      render: (v: number | null) => (v == null ? '—' : `×${v.toFixed(2)}`),
    },
    {
      title: 'Очередь',
      width: 132,
      render: (_, row) => {
        const load = workload[row.developer_id];
        if (!load) return '—';
        return (
          <Tooltip title={`Свободно ${load.available_hours} ч на неделю вперёд`}>
            <span style={{ color: load.overloaded ? '#ff6b6b' : undefined }}>
              {load.queue_hours} ч
              {load.queue_days != null ? ` ≈ ${load.queue_days} дн` : ''}
              {load.without_estimate > 0 ? ` +${load.without_estimate} б/о` : ''}
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: 'Замечания',
      width: 156,
      render: (_, row) =>
        FLAG_ORDER.filter((f) => row.flag_counts[f]).map((flag) => (
          <Tooltip key={flag} title={FLAG_LABELS[flag]}>
            <Tag color={COLOR[flag]}>{ICON[flag]} {row.flag_counts[flag]}</Tag>
          </Tooltip>
        )) || '—',
    },
  ];

  const totals = developers.reduce(
    (acc, d) => ({
      total: acc.total + d.total_issues,
      dev: acc.dev + d.in_dev,
      waiting: acc.waiting + d.waiting,
      todo: acc.todo + d.todo,
      est: acc.est + d.est_hours,
      fact: acc.fact + d.fact_hours,
    }),
    { total: 0, dev: 0, waiting: 0, todo: 0, est: 0, fact: 0 },
  );

  return (
    <Table<DeskDeveloper>
      size="small"
      rowKey="developer_id"
      dataSource={developers}
      columns={columns}
      pagination={false}
      // Ширины по макету: имя забирает остаток, цифры узкие.
      scroll={{ x: 1000 }}
      onRow={(row) => ({
        onClick: () => onSelect(selected === row.developer_id ? null : row.developer_id),
        style: {
          cursor: 'pointer',
          background: selected === row.developer_id ? 'rgba(75,163,255,0.12)' : undefined,
        },
      })}
      summary={() => (
        <Table.Summary.Row>
          <Table.Summary.Cell index={0}>Итого · {developers.length}</Table.Summary.Cell>
          <Table.Summary.Cell index={1} align="right">{totals.total}</Table.Summary.Cell>
          <Table.Summary.Cell index={2} align="right">{totals.dev}</Table.Summary.Cell>
          <Table.Summary.Cell index={3} align="right">{totals.waiting}</Table.Summary.Cell>
          <Table.Summary.Cell index={4} align="right">{totals.todo}</Table.Summary.Cell>
          <Table.Summary.Cell index={5}>
            <HoursScale fact={totals.fact} est={totals.est || null} overrunPct={overrunPct} width={150} />
          </Table.Summary.Cell>
          <Table.Summary.Cell index={6} align="right">—</Table.Summary.Cell>
          <Table.Summary.Cell index={7} />
          <Table.Summary.Cell index={8} />
        </Table.Summary.Row>
      )}
    />
  );
}
