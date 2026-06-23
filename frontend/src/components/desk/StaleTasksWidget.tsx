import { Avatar, Tag } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { statusTagColor } from '../../utils/status';
import type { StaleTask, StaleTasksData } from '../../types/desk';

function daysWord(n: number): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return 'дней';
  if (b > 1 && b < 5) return 'дня';
  if (b === 1) return 'день';
  return 'дней';
}

function Row({ task, personLabel }: { task: StaleTask; personLabel: string }) {
  const label = `${task.key ? `${task.key} · ` : ''}${task.title ?? '—'}`;
  return (
    <div className="desk-stale-item">
      <div className="desk-stale-top">
        <div className="desk-stale-title">
          {task.url ? (
            <a href={task.url} target="_blank" rel="noreferrer">{label}</a>
          ) : (
            label
          )}
        </div>
        <div className="desk-stale-age" title="Дней без изменений в Jira">
          {task.days_idle} {daysWord(task.days_idle)}
        </div>
      </div>
      <div className="desk-stale-sub">
        {task.status && (
          <Tag color={statusTagColor(task.status, task.status_category)}>{task.status}</Tag>
        )}
        <span className="desk-stale-person">
          <Avatar size={18} src={task.person.avatar_url ?? undefined}>
            {(task.person.name ?? '?').slice(0, 1)}
          </Avatar>
          {personLabel}: {task.person.name ?? 'не назначен'}
        </span>
      </div>
    </div>
  );
}

function Column({
  heading,
  hint,
  tasks,
  personLabel,
}: {
  heading: string;
  hint: string;
  tasks: StaleTask[];
  personLabel: string;
}) {
  return (
    <div className="desk-stale-col">
      <div className="desk-stale-col-head">{heading}</div>
      <div className="desk-stale-col-hint">{hint}</div>
      {tasks.length === 0 ? (
        <div className="desk-empty">Нет залежавшихся задач</div>
      ) : (
        tasks.map((t, i) => (
          <Row key={`${t.key ?? ''}-${i}`} task={t} personLabel={personLabel} />
        ))
      )}
    </div>
  );
}

export default function StaleTasksWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<StaleTasksData>(token, 'stale_tasks');
  const myTasks = data?.my_tasks ?? [];
  const assigned = data?.assigned ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={myTasks.length === 0 && assigned.length === 0}
      emptyText="Нет залежавшихся задач"
    >
      <div className="desk-stale-grid">
        <Column
          heading="Мои задачи"
          hint="Создал я, дольше всего без касания"
          tasks={myTasks}
          personLabel="исполнитель"
        />
        <Column
          heading="Задачи мне"
          hint="Назначены мне, дольше всего без касания"
          tasks={assigned}
          personLabel="автор"
        />
      </div>
    </WidgetShell>
  );
}
