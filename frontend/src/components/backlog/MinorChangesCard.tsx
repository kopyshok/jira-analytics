import { useState } from 'react';
import { Alert, Card, Collapse, Empty, Spin, Statistic, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMinorChangesSummary } from '../../hooks/useBacklog';
import type { MinorChangeTask, MinorChangesTeam, MinorRoleHours } from '../../api/backlog';

const ROLE_LABEL: Record<keyof MinorRoleHours, string> = {
  analyst: 'Аналитик',
  dev: 'Разработчик',
  qa: 'Тестирование',
  opo: 'ОПЭ',
};

const fmt = (h: number) => `${Math.round(h * 10) / 10} ч`.replace('.', ',');

interface Props {
  /** Команды шапки через запятую; пусто — все команды. */
  teams?: string;
  jiraBaseUrl: string;
}

/** Часы по ролям одной строкой; ОПЭ — только если есть. */
function roleLine(hours: Record<string, number | null>): string {
  const parts = (Object.keys(ROLE_LABEL) as (keyof MinorRoleHours)[])
    .filter((r) => r !== 'opo' || hours[r])
    .map((r) => `${ROLE_LABEL[r]} ${fmt(hours[r] ?? 0)}`);
  return parts.join(' · ');
}

function TeamBlock({ block, jiraBaseUrl }: { block: MinorChangesTeam; jiraBaseUrl: string }) {
  const [open, setOpen] = useState(false);
  const link = (key: string) =>
    jiraBaseUrl ? (
      <a href={`${jiraBaseUrl}/browse/${key}`} target="_blank" rel="noreferrer">{key}</a>
    ) : (
      <span>{key}</span>
    );

  const columns: ColumnsType<MinorChangeTask> = [
    { title: 'Задача', dataIndex: 'key', width: 110, render: (k: string) => link(k) },
    { title: 'Название', dataIndex: 'title' },
    { title: 'Статус', dataIndex: 'status', width: 150, render: (s: string) => <Tag>{s}</Tag> },
    { title: 'Исполнитель', dataIndex: 'assignee', width: 160, render: (a: string | null) => a ?? '—' },
    {
      title: 'Оценка',
      dataIndex: 'hours',
      width: 280,
      render: (h: MinorRoleHours) =>
        Object.values(h).some((v) => v) ? roleLine(h) : <Typography.Text type="secondary">без оценки</Typography.Text>,
    },
    {
      title: 'Эпик',
      dataIndex: 'epic_key',
      width: 220,
      render: (k: string | null, r) =>
        k ? <>{link(k)} <Typography.Text type="secondary">{r.epic_summary}</Typography.Text></> : '—',
    },
  ];

  const stats = [
    { title: 'Открыто', value: `${block.open_count} шт.` },
    {
      title: 'С оценкой',
      value: `${block.estimated_count} шт. · ${fmt(block.hours.total)}`,
      note: block.estimated_count ? roleLine(block.hours) : undefined,
    },
    { title: 'Без оценки', value: `${block.unestimated_count} шт.` },
    ...(block.reserve_hours != null
      ? [{ title: 'Заложено на квартал', value: fmt(block.reserve_hours) }]
      : []),
  ];

  return (
    <Card size="small" title={block.team} style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 32 }}>
        {stats.map((s) => (
          <div key={s.title}>
            <Statistic title={s.title} value={s.value} styles={{ content: { fontSize: 20 } }} />
            {s.note && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{s.note}</Typography.Text>}
          </div>
        ))}
      </div>
      <Collapse
        ghost
        style={{ marginTop: 8 }}
        activeKey={open ? ['tasks'] : []}
        onChange={(keys) => setOpen(keys.length > 0)}
        items={[{
          key: 'tasks',
          label: `Список задач (${block.tasks.length})`,
          children: block.tasks.length ? (
            <Table<MinorChangeTask>
              size="small"
              rowKey="key"
              columns={columns}
              dataSource={block.tasks}
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Открытых минорных задач нет" />
          ),
        }]}
      />
    </Card>
  );
}

/** Сводка минорных изменений по командам шапки — над таблицей «Целевых задач». */
export default function MinorChangesCard({ teams, jiraBaseUrl }: Props) {
  const { data, isLoading, error } = useMinorChangesSummary(teams);
  if (isLoading) return <Spin />;
  if (error || !data) {
    return <Alert type="error" showIcon title="Не удалось загрузить минорные изменения" />;
  }
  if (!data.teams.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Минорных изменений нет" />;
  }
  return (
    <div>
      {data.teams.map((t) => <TeamBlock key={t.team} block={t} jiraBaseUrl={jiraBaseUrl} />)}
    </div>
  );
}
