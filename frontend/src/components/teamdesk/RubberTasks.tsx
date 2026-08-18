import { Card, InputNumber, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { roundHours, type DeskIssue } from '../../api/teamDesk';
import { IssueKey } from './IssueCells';

interface Props {
  issues: DeskIssue[];
  /** Сколько дней нормы уходит в очередь — настройка раздела. */
  rubberDays: number;
  jiraBaseUrl?: string;
  onDailyRate: (issueId: string, hours: number | null) => void;
}

/**
 * Все «резиновые» задачи среза одним списком: по каким задачам очередь
 * считается по дневной норме и сколько из них в неё уходит.
 */
export function RubberTasks({ issues, rubberDays, jiraBaseUrl, onDailyRate }: Props) {
  const rows = issues.filter((issue) => issue.daily_rate);
  if (!rows.length) return null;

  const left = (row: DeskIssue) =>
    row.est_hours == null ? null : Math.max(0, row.est_hours - row.fact_hours);

  const columns: ColumnsType<DeskIssue> = [
    { title: 'Разработчик', width: 220, ellipsis: true,
      render: (_, row) => row.developer_name ?? '—' },
    {
      title: 'Задача',
      ellipsis: true,
      render: (_, row) => (
        <span>
          <IssueKey issueKey={row.key} jiraBaseUrl={jiraBaseUrl} /> {row.summary}
        </span>
      ),
    },
    { title: 'Статус', width: 170, render: (_, row) => row.status },
    {
      title: 'Ч/день',
      width: 110,
      align: 'right',
      render: (_, row) => (
        <InputNumber
          size="small"
          min={0}
          max={24}
          step={0.5}
          value={row.daily_rate ?? null}
          onChange={(v) => onDailyRate(row.id, v == null ? null : Number(v))}
          style={{ width: 84 }}
        />
      ),
    },
    { title: 'Оценка', width: 96, align: 'right',
      render: (_, row) => (row.est_hours == null ? '—' : roundHours(row.est_hours)) },
    { title: 'Факт', width: 88, align: 'right',
      render: (_, row) => roundHours(row.fact_hours) },
    { title: 'Осталось', width: 104, align: 'right',
      render: (_, row) => {
        const value = left(row);
        return value == null ? '—' : roundHours(value);
      } },
    {
      title: 'В очередь',
      width: 116,
      align: 'right',
      render: (_, row) => {
        const value = left(row);
        if (value == null) return '—';
        return roundHours(Math.min(value, (row.daily_rate ?? 0) * rubberDays));
      },
    },
  ];

  return (
    <Card
      size="small"
      title="Резиновые задачи"
      extra={
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          в очередь идёт норма за {rubberDays} дн, но не больше остатка
        </Typography.Text>
      }
    >
      <Table<DeskIssue>
        size="small"
        rowKey="id"
        dataSource={rows}
        columns={columns}
        pagination={false}
        scroll={{ x: 1100 }}
      />
    </Card>
  );
}
