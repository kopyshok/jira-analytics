import { useState } from 'react';
import {
  Button, Card, Popconfirm, Space, Switch, Table, Tag, Tooltip, App,
} from 'antd';
import { PlusOutlined, DeleteOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getSchedules, updateSchedule, deleteSchedule, runScheduleNow,
  type SyncScheduleOut,
} from '../../api/syncSchedule';
import type { PipelineMode } from '../../api/syncRuns';
import ScheduleEditorModal from './ScheduleEditorModal';

const MODE_LABELS: Record<PipelineMode, string> = {
  quick: 'Быстрый',
  normal: 'Обычный',
  full: 'Полный',
  team: 'По команде',
};

export default function SyncSchedule() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const { data: schedules = [], isLoading } = useQuery({
    queryKey: ['sync', 'schedule'],
    queryFn: getSchedules,
  });

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<SyncScheduleOut | null>(null);

  const openCreate = () => { setEditing(null); setEditorOpen(true); };
  const openEdit = (row: SyncScheduleOut) => { setEditing(row); setEditorOpen(true); };
  const closeEditor = () => setEditorOpen(false);
  const onSaved = () => {
    qc.invalidateQueries({ queryKey: ['sync', 'schedule'] });
    notification.success({
      title: editing ? 'Расписание обновлено' : 'Расписание создано',
    });
  };

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateSchedule(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'schedule'] }),
    onError: (e) =>
      notification.error({ title: 'Ошибка', description: (e as Error).message }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSchedule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'schedule'] }),
    onError: (e) =>
      notification.error({ title: 'Ошибка удаления', description: (e as Error).message }),
  });

  const runNowMut = useMutation({
    mutationFn: (id: string) => runScheduleNow(id),
    onSuccess: () => {
      notification.success({ title: 'Запущено' });
      qc.invalidateQueries({ queryKey: ['sync', 'runs'] });
    },
    onError: (e) =>
      notification.error({ title: 'Ошибка запуска', description: (e as Error).message }),
  });

  const stop = (e: React.MouseEvent | React.SyntheticEvent) => e.stopPropagation();

  const columns = [
    {
      title: 'Название',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Расписание',
      dataIndex: 'description',
      key: 'description',
      render: (desc: string, r: SyncScheduleOut) => (
        <Tooltip title={r.cron_expr}>
          <span>{desc}</span>
        </Tooltip>
      ),
    },
    {
      title: 'Режим',
      dataIndex: 'mode',
      key: 'mode',
      render: (v: PipelineMode) => <Tag>{MODE_LABELS[v] ?? v}</Tag>,
    },
    {
      title: 'Команда',
      dataIndex: 'team',
      key: 'team',
      render: (v: string | null) => v ?? <span style={{ color: '#888' }}>—</span>,
    },
    {
      title: 'Вкл',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (v: boolean, r: SyncScheduleOut) => (
        <span onClick={stop}>
          <Switch
            checked={v}
            size="small"
            loading={toggleMut.isPending}
            onChange={(checked) => toggleMut.mutate({ id: r.id, enabled: checked })}
          />
        </span>
      ),
    },
    {
      title: '',
      key: 'actions',
      render: (_: unknown, r: SyncScheduleOut) => (
        <Space size={4} onClick={stop}>
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            loading={runNowMut.isPending}
            onClick={() => runNowMut.mutate(r.id)}
          >
            Запустить
          </Button>
          <Popconfirm
            title="Удалить расписание?"
            okText="Да"
            cancelText="Нет"
            onConfirm={() => deleteMut.mutate(r.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="Расписание автозапуска"
      size="small"
      extra={
        <Button
          size="small"
          icon={<PlusOutlined />}
          onClick={openCreate}
        >
          Добавить
        </Button>
      }
    >
      <Table<SyncScheduleOut>
        dataSource={schedules}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        onRow={(row) => ({
          onClick: () => openEdit(row),
          style: { cursor: 'pointer' },
        })}
      />

      <ScheduleEditorModal
        open={editorOpen}
        schedule={editing}
        onClose={closeEditor}
        onSaved={onSaved}
      />
    </Card>
  );
}
