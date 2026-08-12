import { useState } from 'react';
import { App, Alert, Button, Card, Select, Space, Spin, Typography } from 'antd';
import type { DeskSettings } from '../../api/teamDesk';
import { useDeskSettings, useSaveDeskSettings } from '../../hooks/useTeamDesk';
import { useRoles } from '../../hooks/useRoles';

const GROUP_TITLES: { key: string; title: string; hint: string }[] = [
  { key: 'dev', title: 'У разработчика', hint: 'Мяч у него: он должен двигать задачу' },
  { key: 'waiting', title: 'Ждут не его', hint: 'Ждёт тестировщика, аналитика или заказчика' },
  { key: 'todo', title: 'Не начаты', hint: 'В очереди, работа ещё не началась' },
  { key: 'done', title: 'Закрыты', hint: 'Готово или отменено' },
];

/**
 * Настройки раздела «Стол тимлида». Статусная модель в Jira меняется, поэтому
 * отнесение статуса к группе — настройка, а не константа в коде.
 */
export default function TeamDeskSettingsTab() {
  const { message } = App.useApp();
  const query = useDeskSettings();
  const save = useSaveDeskSettings();
  const rolesQuery = useRoles();
  const [draft, setDraft] = useState<DeskSettings | null>(null);

  if (query.isLoading) return <Spin />;
  if (!query.data) return <Alert type="error" title="Не удалось загрузить настройки" />;

  const current = draft ?? query.data;
  const dirty = draft != null && JSON.stringify(draft) !== JSON.stringify(query.data);

  const patch = (next: Partial<DeskSettings>) => setDraft({ ...current, ...next });

  const setGroup = (group: string, statuses: string[]) =>
    patch({ status_groups: { ...current.status_groups, [group]: statuses } });

  const known = new Set(Object.values(current.status_groups).flat());

  return (
    <Space orientation="vertical" size={14} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        title="Статусы вводятся вручную — ровно так, как они называются в Jira."
        description="Статус, не попавший ни в одну группу, не ломает расчёты: он показывается как нераспределённый."
      />

      <Card size="small" title="Группы статусов">
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          {GROUP_TITLES.map((g) => (
            <div key={g.key}>
              <Typography.Text strong>{g.title}</Typography.Text>{' '}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{g.hint}</Typography.Text>
              <Select
                mode="tags"
                style={{ width: '100%', marginTop: 4 }}
                value={current.status_groups[g.key] ?? []}
                onChange={(v) => setGroup(g.key, v)}
                tokenSeparators={[',']}
                placeholder="Введите название статуса и нажмите Enter"
              />
            </div>
          ))}
        </Space>
      </Card>

      <Card size="small" title="Очередь работы">
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          Статусы, задачи в которых считаются нагрузкой разработчика на ближайшие дни.
        </Typography.Paragraph>
        <Select
          mode="tags"
          style={{ width: '100%' }}
          value={current.queue_statuses}
          onChange={(v) => patch({ queue_statuses: v })}
          tokenSeparators={[',']}
        />
        {current.queue_statuses.some((s) => !known.has(s)) && (
          <Typography.Text type="warning" style={{ fontSize: 12 }}>
            Часть статусов очереди не отнесена ни к одной группе выше.
          </Typography.Text>
        )}
      </Card>

      <Card size="small" title="Работа идёт руками">
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          Статусы, в которых разработчик делает задачу прямо сейчас. По ним считается
          виджет «Задач в работе одновременно» и лимит к нему. Группа «у разработчика»
          шире: код-ревью и ожидание помещения мяч тоже держат за ним, но одновременной
          работой не являются.
        </Typography.Paragraph>
        <Select
          mode="tags"
          style={{ width: '100%' }}
          value={current.wip_statuses}
          onChange={(v) => patch({ wip_statuses: v })}
          tokenSeparators={[',']}
          placeholder="Например: В РАБОТЕ"
        />
      </Card>

      <Card size="small" title="Не показывать">
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          Статусы, которых в разделе быть не должно вовсе: задача ещё не взята в работу,
          смотреть на неё нечего. Такие задачи не идут ни в список, ни в счётчики, ни в
          очередь работы.
        </Typography.Paragraph>
        <Select
          mode="tags"
          style={{ width: '100%' }}
          value={current.hidden_statuses}
          onChange={(v) => patch({ hidden_statuses: v })}
          tokenSeparators={[',']}
          placeholder="Например: Backlog"
        />
      </Card>

      <Card size="small" title="Кто попадает в срез">
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          Роли сотрудников, задачи которых показывает раздел. Аналитики, руководители
          проектов и консультанты в срез не идут — даже если задача назначена на них.
        </Typography.Paragraph>
        <Select
          mode="multiple"
          style={{ width: '100%' }}
          value={current.developer_roles}
          onChange={(v) => patch({ developer_roles: v })}
          loading={rolesQuery.isLoading}
          options={(rolesQuery.data ?? []).map((r) => ({ value: r.code, label: r.label }))}
        />
      </Card>

      <Card size="small" title="Типы задач">
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Typography.Text strong>Считаются декомпозицией</Typography.Text>{' '}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              наличие таких потомков снимает признак «без декомпозиции»
            </Typography.Text>
            <Select
              mode="tags"
              style={{ width: '100%', marginTop: 4 }}
              value={current.subtask_types}
              onChange={(v) => patch({ subtask_types: v })}
              tokenSeparators={[',']}
            />
          </div>
          <div>
            <Typography.Text strong>Берутся по исполнителю</Typography.Text>{' '}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              технический анализ: поле «Разработчик» пустое, работу делает исполнитель
            </Typography.Text>
            <Select
              mode="tags"
              style={{ width: '100%', marginTop: 4 }}
              value={current.assignee_types}
              onChange={(v) => patch({ assignee_types: v })}
              tokenSeparators={[',']}
            />
          </div>
        </Space>
      </Card>

      <Space>
        <Button
          type="primary"
          disabled={!dirty}
          loading={save.isPending}
          onClick={() =>
            save.mutate(current, {
              onSuccess: () => {
                setDraft(null);
                message.success('Настройки сохранены');
              },
            })
          }
        >
          Сохранить
        </Button>
        <Button disabled={!dirty} onClick={() => setDraft(null)}>Отменить</Button>
      </Space>
    </Space>
  );
}
