import { useMemo, useState } from 'react';
import {
  Table, Button, Space, App, Tag, Avatar, Modal, Checkbox, Popconfirm, Tooltip,
} from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import { useEmployees } from '../../hooks/useCapacity';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import {
  useWorkDesks, useCreateDesk, useUpdateDeskWidgets, useRevokeDesk, useRegenerateDesk,
} from '../../hooks/useWorkDesks';
import { WIDGET_CATALOG } from '../desk/widgetCatalog';
import { copyText } from '../../utils/clipboard';
import type { WorkDeskListItem } from '../../api/workDesks';

interface Row {
  employee_id: string;
  display_name: string;
  avatar_url: string | null;
  desk: WorkDeskListItem | null;
}

const ALL_WIDGET_KEYS = WIDGET_CATALOG.map((w) => w.key);

export default function WorkDesksTab() {
  const { message } = App.useApp();
  const { queryParams } = useGlobalTeamFilter();
  const { data: employees } = useEmployees({ withTeams: true });
  const { data: desks, isLoading } = useWorkDesks();

  const createDesk = useCreateDesk();
  const updateWidgets = useUpdateDeskWidgets();
  const revokeDesk = useRevokeDesk();
  const regenerateDesk = useRegenerateDesk();

  const [modalOpen, setModalOpen] = useState(false);
  const [editRow, setEditRow] = useState<Row | null>(null);
  const [checked, setChecked] = useState<string[]>([]);

  const selectedTeams = useMemo(
    () => (queryParams.teams ? queryParams.teams.split(',').filter(Boolean) : []),
    [queryParams.teams],
  );

  const deskByEmpId = useMemo(() => {
    const m = new Map<string, WorkDeskListItem>();
    (desks ?? []).forEach((d) => m.set(d.employee.id, d));
    return m;
  }, [desks]);

  const rows: Row[] = useMemo(() => {
    const teamMatch = (teams: { team: string }[] | undefined): boolean => {
      if (selectedTeams.length === 0) return true;
      return (teams ?? []).some((t) => selectedTeams.includes(t.team));
    };
    return (employees ?? [])
      .filter((e) => e.is_active && teamMatch(e.teams))
      .map((e) => ({
        employee_id: e.id,
        display_name: e.display_name,
        avatar_url: e.avatar_url,
        desk: deskByEmpId.get(e.id) ?? null,
      }))
      .sort((a, b) => a.display_name.localeCompare(b.display_name, 'ru'));
  }, [employees, selectedTeams, deskByEmpId]);

  const openCreate = (row: Row) => {
    setEditRow(row);
    setChecked(ALL_WIDGET_KEYS);
    setModalOpen(true);
  };

  const openEdit = (row: Row) => {
    setEditRow(row);
    setChecked(row.desk?.enabled_widgets ?? []);
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditRow(null);
  };

  const submitModal = () => {
    if (!editRow) return;
    if (editRow.desk) {
      updateWidgets.mutate(
        { id: editRow.desk.id, enabled_widgets: checked },
        {
          onSuccess: () => { message.success('Виджеты обновлены'); closeModal(); },
          onError: (e) => message.error(e.message),
        },
      );
    } else {
      createDesk.mutate(
        { employee_id: editRow.employee_id, enabled_widgets: checked },
        {
          onSuccess: () => { message.success('Стол создан'); closeModal(); },
          onError: (e) => message.error(e.message),
        },
      );
    }
  };

  const copyLink = async (desk: WorkDeskListItem) => {
    if (!desk.desk_url_path) return;
    const url = window.location.origin + desk.desk_url_path;
    if (await copyText(url)) {
      message.success('Ссылка скопирована');
    } else {
      message.error('Не удалось скопировать ссылку');
    }
  };

  const columns = [
    {
      title: 'Сотрудник',
      key: 'employee',
      render: (_: unknown, r: Row) => (
        <Space>
          <Avatar size={28} src={r.avatar_url}>
            {r.display_name.slice(0, 1)}
          </Avatar>
          <span>{r.display_name}</span>
        </Space>
      ),
    },
    {
      title: 'Статус стола',
      key: 'status',
      width: 140,
      render: (_: unknown, r: Row) =>
        r.desk ? <Tag color="green">Активен</Tag> : <Tag>Нет</Tag>,
    },
    {
      title: 'Ссылка',
      key: 'link',
      width: 200,
      render: (_: unknown, r: Row) => (
        <Button
          size="small"
          icon={<LinkOutlined />}
          disabled={!r.desk}
          onClick={() => r.desk && copyLink(r.desk)}
        >
          Копировать ссылку
        </Button>
      ),
    },
    {
      title: 'Действия',
      key: 'actions',
      render: (_: unknown, r: Row) =>
        r.desk ? (
          <Space wrap>
            <Button size="small" onClick={() => openEdit(r)}>Изменить виджеты</Button>
            <Popconfirm
              title="Перевыпустить стол?"
              description="Старая ссылка перестанет работать."
              okText="Перевыпустить"
              cancelText="Отмена"
              onConfirm={() =>
                regenerateDesk.mutate(r.desk!.id, {
                  onSuccess: () => message.success('Стол перевыпущен'),
                  onError: (e) => message.error(e.message),
                })
              }
            >
              <Button size="small">Перевыпустить</Button>
            </Popconfirm>
            <Popconfirm
              title="Отозвать стол?"
              description="Ссылка перестанет работать."
              okText="Отозвать"
              okButtonProps={{ danger: true }}
              cancelText="Отмена"
              onConfirm={() =>
                revokeDesk.mutate(r.desk!.id, {
                  onSuccess: () => message.success('Стол отозван'),
                  onError: (e) => message.error(e.message),
                })
              }
            >
              <Button size="small" danger>Отозвать</Button>
            </Popconfirm>
          </Space>
        ) : (
          <Button size="small" type="primary" onClick={() => openCreate(r)}>Создать</Button>
        ),
    },
  ];

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Tooltip title="Список сотрудников ваших команд. Создайте стол и поделитесь публичной ссылкой.">
        <span style={{ color: 'var(--ant-color-text-secondary, #999)' }}>
          Рабочие столы аналитиков — публичные ссылки без входа в систему.
        </span>
      </Tooltip>
      <Table
        dataSource={rows}
        rowKey="employee_id"
        loading={isLoading}
        columns={columns}
        pagination={false}
        size="small"
      />
      <Modal
        title={editRow?.desk ? `Виджеты: ${editRow.display_name}` : `Новый стол: ${editRow?.display_name ?? ''}`}
        open={modalOpen}
        onCancel={closeModal}
        onOk={submitModal}
        okText={editRow?.desk ? 'Сохранить' : 'Создать'}
        cancelText="Отмена"
        confirmLoading={createDesk.isPending || updateWidgets.isPending}
      >
        <Checkbox.Group
          value={checked}
          onChange={(v) => setChecked(v as string[])}
          style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
          options={WIDGET_CATALOG.map((w) => ({ value: w.key, label: w.label }))}
        />
      </Modal>
    </Space>
  );
}
