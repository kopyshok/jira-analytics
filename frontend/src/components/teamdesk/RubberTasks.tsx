import { Card, InputNumber, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { roundHours, type DeskIssue } from '../../api/teamDesk';
import { IssueKey } from './IssueCells';
import { STATUS_GROUP_TONE, deskAvatarTone, deskInitials } from '../../utils/teamDeskView';

interface Props {
  issues: DeskIssue[];
  /** Сколько дней нормы уходит в очередь — настройка раздела. */
  rubberDays: number;
  jiraBaseUrl?: string;
  onDailyRate: (issueId: string, hours: number | null) => void;
  /**
   * Компактный вид скина: заголовок и карточка на задачу для узкой колонки;
   * без задач — спокойная подсказка вместо пустоты.
   */
  compact?: boolean;
}

/**
 * Все «резиновые» задачи среза одним списком: по каким задачам очередь
 * считается по дневной норме и сколько из них в неё уходит.
 */
export function RubberTasks({ issues, rubberDays, jiraBaseUrl, onDailyRate, compact = false }: Props) {
  const rows = issues.filter((issue) => issue.daily_rate);
  if (!rows.length && !compact) return null;

  const left = (row: DeskIssue) =>
    row.est_hours == null ? null : Math.max(0, row.est_hours - row.fact_hours);
  // Оценка — только потолок: нет её — вклад задаёт дневная норма.
  const toQueue = (row: DeskIssue) => {
    const byRate = (row.daily_rate ?? 0) * rubberDays;
    const value = left(row);
    return roundHours(value == null ? byRate : Math.min(byRate, value));
  };

  if (compact) {
    return (
      <>
        <h2 className="rpc-card-title">Резиновые задачи · {rows.length}</h2>
        {rows.length ? (
          <p className="tdc-note">в очередь идёт норма за {rubberDays} дн, но не больше остатка</p>
        ) : (
          <p className="tdc-empty">Нет — норма в день задаётся в колонке DevForDay</p>
        )}
        {rows.map((row) => {
          const tone = deskAvatarTone(row.developer_name);
          const rest = left(row);
          return (
            <div key={row.id} className="tdc-rubber">
              <div className="tdc-rubber-head">
                <span className="tdc-avatar" style={{ background: tone.bg, color: tone.fg }}>
                  {deskInitials(row.developer_name)}
                </span>
                <b className="tdc-ellipsis">{row.developer_name ?? '—'}</b>
                <span className={`wr-pill is-sm is-${STATUS_GROUP_TONE[row.status_group]}`}>{row.status}</span>
              </div>
              <div className="tdc-rubber-task">
                <IssueKey issueKey={row.key} jiraBaseUrl={jiraBaseUrl} /> {row.summary}
              </div>
              <div className="tdc-rubber-stats">
                <div>
                  <InputNumber
                    size="small"
                    min={0}
                    max={24}
                    step={0.5}
                    value={row.daily_rate ?? null}
                    onChange={(v) => onDailyRate(row.id, v == null ? null : Number(v))}
                    aria-label={`Часов в день: ${row.key}`}
                    style={{ width: 56 }}
                  />
                  <span>ч/день</span>
                </div>
                <div><b>{row.est_hours == null ? '—' : roundHours(row.est_hours)}</b><span>оценка</span></div>
                <div><b>{roundHours(row.fact_hours)}</b><span>факт</span></div>
                <div><b>{rest == null ? '—' : roundHours(rest)}</b><span>осталось</span></div>
                <div className="is-accent"><b>{toQueue(row)}</b><span>в очередь</span></div>
              </div>
            </div>
          );
        })}
      </>
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
