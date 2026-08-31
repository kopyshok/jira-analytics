import { useState } from 'react';
import {
  Alert,
  App,
  Button,
  Input,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { Subgroup, TeamRegistryRow } from '../../api/teams';
import {
  useAddSubgroup,
  useDeleteSubgroup,
  useRenameSubgroup,
  useSetTeamHasSubgroups,
  useTeamRegistry,
} from '../../hooks/useTeamRegistry';

/** Список групп одной команды: переименование по месту, добавление, удаление. */
function SubgroupList({ team }: { team: TeamRegistryRow }) {
  const { notification } = App.useApp();
  const add = useAddSubgroup();
  const rename = useRenameSubgroup();
  const remove = useDeleteSubgroup();
  const [draft, setDraft] = useState('');

  const onAdd = () => {
    const name = draft.trim();
    if (!name) return;
    add.mutate(
      { team: team.name, name },
      {
        onSuccess: () => setDraft(''),
        onError: () => notification.error({ title: 'Не удалось добавить группу' }),
      },
    );
  };

  const onRename = (group: Subgroup, next: string) => {
    const name = next.trim();
    if (!name || name === group.name) return;
    rename.mutate({ id: group.id, name });
  };

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={8}>
      {team.subgroups.map((g) => (
        <Space key={g.id}>
          <Input
            defaultValue={g.name}
            style={{ width: 260 }}
            onBlur={(e) => onRename(g, e.target.value)}
            onPressEnter={(e) => (e.target as HTMLInputElement).blur()}
          />
          <Popconfirm
            title="Удалить группу?"
            description="Сотрудники и задачи останутся в команде, просто без группы."
            okText="Удалить"
            cancelText="Отмена"
            onConfirm={() => remove.mutate(g.id)}
          >
            <Button danger type="text" icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ))}
      <Space>
        <Input
          placeholder="Название группы"
          style={{ width: 260 }}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onPressEnter={onAdd}
        />
        <Button icon={<PlusOutlined />} onClick={onAdd} loading={add.isPending}>
          Добавить
        </Button>
      </Space>
    </Space>
  );
}

export default function TeamsRegistryTab() {
  const { notification } = App.useApp();
  const { data: teams = [], isLoading } = useTeamRegistry();
  const toggle = useSetTeamHasSubgroups();

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Alert
        type="info"
        showIcon
        message="Группы — деление внутри команды"
        description={
          <>
            В Jira такого деления нет, оно живёт только здесь. Каждая группа планируется
            на квартал отдельно, но ресурсное планирование остаётся общим по команде —
            иначе не видно, что человек занят у соседей. Выключение переключателя
            скрывает разрезы, но ничего не удаляет.
          </>
        }
      />
      <Table<TeamRegistryRow>
        rowKey="name"
        loading={isLoading}
        dataSource={teams}
        pagination={false}
        columns={[
          {
            title: 'Команда',
            dataIndex: 'name',
            render: (name: string, row) => (
              <Space>
                <Typography.Text strong>{name}</Typography.Text>
                {row.has_subgroups && <Tag color="blue">{row.subgroups.length} гр.</Tag>}
              </Space>
            ),
          },
          {
            title: 'Делится на группы',
            dataIndex: 'has_subgroups',
            width: 180,
            render: (enabled: boolean, row) => (
              <Switch
                checked={enabled}
                loading={toggle.isPending && toggle.variables?.name === row.name}
                onChange={(next) =>
                  toggle.mutate(
                    { name: row.name, enabled: next },
                    {
                      onError: () =>
                        notification.error({ title: 'Не удалось сохранить признак' }),
                    },
                  )
                }
              />
            ),
          },
        ]}
        expandable={{
          rowExpandable: (row) => row.has_subgroups,
          expandedRowRender: (row) => <SubgroupList team={row} />,
        }}
      />
    </Space>
  );
}
