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
  /** Списком для узкой колонки: задача строкой и четыре цифры под ней (обложки). */
  compact?: boolean;
}

/**
 * Все «резиновые» задачи среза одним списком: по каким задачам очередь
 * считается по дневной норме и сколько из них в неё уходит.
 */
export function RubberTasks({ issues, rubberDays, jiraBaseUrl, onDailyRate, compact = false }: Props) {
  const rows = issues.filter((issue) => issue.daily_rate);
  // В узкой колонке обложки блок стоит всегда — пустым он говорит, что таких задач нет.
  if (!rows.length) {
    return compact ? (
      <section className="desk-rubber">
        <div className="sw-block-title">
          <span className="sw-block-num">1.5</span>
          <b>Резиновые задачи · 0</b>
        </div>
        <p className="desk-rubber-note">
          Резиновых задач в срезе нет. Задача становится резиновой, когда в списке задач ей задана норма в колонке «DevForDay».
        </p>
      </section>
    ) : null;
  }

  const left = (row: DeskIssue) =>
    row.est_hours == null ? null : Math.max(0, row.est_hours - row.fact_hours);
  // Оценка — только потолок: нет её — вклад задаёт дневная норма.
  const toQueue = (row: DeskIssue) => {
    const byRate = (row.daily_rate ?? 0) * rubberDays;
    const value = left(row);
    return roundHours(value == null ? byRate : Math.min(byRate, value));
  };
  const rateInput = (row: DeskIssue) => (
    <InputNumber
      size="small"
      min={0}
      max={24}
      step={0.5}
      value={row.daily_rate ?? null}
      onChange={(v) => onDailyRate(row.id, v == null ? null : Number(v))}
      style={{ width: 84 }}
    />
  );

  if (compact) {
    return (
      <section className="desk-rubber">
        <div className="sw-block-title">
          <span className="sw-block-num">1.5</span>
          <b>Резиновые задачи · {rows.length}</b>
        </div>
        <p className="desk-rubber-note">в очередь идёт норма за {rubberDays} дн, но не больше остатка</p>
        {rows.map((row) => {
          const rest = left(row);
          return (
            <div key={row.id} className="desk-rubber-item">
              <div className="desk-rubber-line">
                <b>{row.developer_name ?? '—'}</b>
                {' · '}
                <IssueKey issueKey={row.key} jiraBaseUrl={jiraBaseUrl} /> {row.summary}
                {' · '}
                <span className="desk-rubber-status">{row.status}</span>
                <span className="desk-rubber-rate">{rateInput(row)} ч/день</span>
              </div>
              <div className="desk-rubber-figures">
                <div><span>оценка</span><b>{row.est_hours == null ? '—' : roundHours(row.est_hours)}</b></div>
                <div><span>факт</span><b>{roundHours(row.fact_hours)}</b></div>
                <div><span>осталось</span><b>{rest == null ? '—' : roundHours(rest)}</b></div>
                <div><span>в очередь</span><b>{toQueue(row)}</b></div>
              </div>
            </div>
          );
        })}
      </section>
    );
  }

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
      render: (_, row) => rateInput(row),
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
      render: (_, row) => toQueue(row),
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
