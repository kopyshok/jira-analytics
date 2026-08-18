import { Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  FLAG_COLOR, FLAG_ICON, FLAG_LABELS, FLAG_ORDER, roundHours,
  type DeskDeveloper, type DeskWorkload, type FlagCode,
} from '../../api/teamDesk';
import type { QueueScope } from './queueFilter';
import { HoursScale } from './HoursScale';

interface Props {
  developers: DeskDeveloper[];
  workload: Record<string, DeskWorkload>;
  overrunPct: number;
  selected: string | null;
  onSelect: (id: string | null) => void;
  /** Статусы-счётчики: по колонке на каждый, в порядке групп. */
  statuses: string[];
  onStatusFilter: (developerId: string, status: string | null) => void;
  queueScope: QueueScope;
  onQueueFilter: (developerId: string, scope: QueueScope) => void;
  flagFilter: FlagCode | null;
  onFlagFilter: (developerId: string, flag: FlagCode | null) => void;
}

/** Раскладка «Ведомость»: строка на разработчика, снизу итог. */
export function DeveloperTable({
  developers, workload, overrunPct, selected, onSelect, statuses, onStatusFilter,
  queueScope, onQueueFilter, flagFilter, onFlagFilter,
}: Props) {
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
    { title: 'Задач', dataIndex: 'total_issues', width: 100, align: 'right',
      sorter: (a, b) => a.total_issues - b.total_issues },
    { title: 'У него', dataIndex: 'in_dev', width: 104, align: 'right',
      sorter: (a, b) => a.in_dev - b.in_dev },
    { title: 'Ждут не его', dataIndex: 'waiting', width: 140, align: 'right',
      sorter: (a, b) => a.waiting - b.waiting },
    { title: 'Не начаты', dataIndex: 'todo', width: 128, align: 'right',
      sorter: (a, b) => a.todo - b.todo },
    {
      title: 'Факт / оценка',
      width: 185,
      render: (_, row) => (
        <HoursScale fact={row.fact_hours} est={row.est_hours || null} overrunPct={overrunPct} width={150} />
      ),
    },
    {
      title: 'Точность',
      dataIndex: 'accuracy',
      width: 120,
      align: 'right',
      sorter: (a, b) => (a.accuracy ?? 0) - (b.accuracy ?? 0),
      render: (v: number | null) => (v == null ? '—' : `×${v.toFixed(2)}`),
    },
    {
      title: 'Очередь',
      width: 210,
      render: (_, row) => {
        const load = workload[row.developer_id];
        if (!load) return '—';
        const active = selected === row.developer_id ? queueScope : null;
        const line = (
          scope: 'all' | 'assigned',
          hours: number,
          days: number | null,
          noEstimate: number,
        ) => (
          <div
            onClick={(e) => {
              e.stopPropagation();
              onQueueFilter(row.developer_id, active === scope ? null : scope);
            }}
            style={{
              cursor: 'pointer',
              borderRadius: 4,
              padding: '0 4px',
              marginInline: -4,
              background: active === scope ? 'rgba(75,163,255,0.18)' : undefined,
            }}
          >
            {scope === 'assigned' && (
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>к вып. </Typography.Text>
            )}
            {roundHours(hours)} ч
            {days != null ? ` ≈ ${days} дн` : ''}
            {noEstimate > 0 ? ` +${noEstimate} б/о` : ''}
          </div>
        );
        return (
          <Tooltip title={`Свободно ${roundHours(load.available_hours)} ч на неделю вперёд`}>
            <div style={{ color: load.overloaded ? '#ff6b6b' : undefined }}>
              {line('all', load.queue_hours, load.queue_days, load.without_estimate)}
              {line(
                'assigned',
                load.assigned_hours,
                load.assigned_days,
                load.assigned_without_estimate,
              )}
            </div>
          </Tooltip>
        );
      },
    },
    {
      title: 'Замечания',
      width: 180,
      render: (_, row) =>
        FLAG_ORDER.filter((f) => row.flag_counts[f]).map((flag) => {
          const active = selected === row.developer_id && flagFilter === flag;
          return (
            <Tooltip key={flag} title={`${FLAG_LABELS[flag]} — показать только эти`}>
              <Tag
                color={FLAG_COLOR[flag]}
                style={{
                  cursor: 'pointer',
                  fontWeight: active ? 700 : undefined,
                  outline: active ? '2px solid #4ba3ff' : undefined,
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  onFlagFilter(row.developer_id, active ? null : flag);
                }}
              >
                {FLAG_ICON[flag]} {row.flag_counts[flag]}
              </Tag>
            </Tooltip>
          );
        }) || '—',
    },
  ];

  // Пустая колонка — шум: показываем статус, если задачи в нём есть хоть у кого-то.
  const statusCols = statuses.filter((status) =>
    developers.some((d) => d.status_counts?.[status]),
  );
  statusCols.forEach((status) => {
    columns.push({
      title: status,
      key: `status:${status}`,
      width: 150,
      align: 'right',
      sorter: (a, b) => (a.status_counts?.[status] ?? 0) - (b.status_counts?.[status] ?? 0),
      render: (_, row) => {
        const count = row.status_counts?.[status] ?? 0;
        if (!count) return <Typography.Text type="secondary">—</Typography.Text>;
        return (
          <Typography.Link
            onClick={(e) => {
              e.stopPropagation();
              onStatusFilter(row.developer_id, status);
            }}
          >
            {count}
          </Typography.Link>
        );
      },
    });
  });

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
      // Имя забирает остаток; цифровым колонкам дана ширина, при которой
      // заголовок помещается в одну строку.
      scroll={{ x: 1370 + statusCols.length * 150 }}
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
          {statusCols.map((status, i) => (
            <Table.Summary.Cell key={status} index={9 + i} align="right">
              {developers.reduce((n, d) => n + (d.status_counts?.[status] ?? 0), 0)}
            </Table.Summary.Cell>
          ))}
        </Table.Summary.Row>
      )}
    />
  );
}
