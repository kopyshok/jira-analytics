import { Card, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { roundHours, type DeskIssue } from '../../api/teamDesk';
import { IssueKey } from './IssueCells';
import { DailyRateInput } from './DailyRateInput';
import { rubberLeft, rubberToQueue } from './deskSignals';

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

  const left = rubberLeft;

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
        <DailyRateInput
          value={row.daily_rate ?? null}
          onCommit={(hours) => onDailyRate(row.id, hours)}
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
      render: (_, row) => roundHours(rubberToQueue(row, rubberDays)),
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
