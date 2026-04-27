import { useState } from 'react';
import {
  Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, App,
} from 'antd';
import { PlusOutlined, DeleteOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  runScheduleNow,
  type SyncScheduleOut,
  type SyncScheduleCreate,
} from '../../api/syncSchedule';
import type { PipelineMode } from '../../api/syncRuns';

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

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateSchedule(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'schedule'] }),
    onError: (e) =>
      notification.error({ message: 'Ошибка', description: (e as Error).message }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSchedule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sync', 'schedule'] }),
    onError: (e) =>
      notification.error({ message: 'Ошибка удаления', description: (e as Error).message }),
  });

  const runNowMut = useMutation({
    mutationFn: (id: string) => runScheduleNow(id),
    onSuccess: () => {
      notification.success({ message: 'Запущено' });
      qc.invalidateQueries({ queryKey: ['sync', 'runs'] });
    },
    onError: (e) =>
      notification.error({ message: 'Ошибка запуска', description: (e as Error).message }),
  });

  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm<SyncScheduleCreate>();

  const createMut = useMutation({
    mutationFn: (body: SyncScheduleCreate) => createSchedule(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sync', 'schedule'] });
      setAddOpen(false);
      form.resetFields();
      notification.success({ message: 'Расписание создано' });
    },
    onError: (e) =>
      notification.error({ message: 'Ошибка создания', description: (e as Error).message }),
  });

  const columns = [
    {
      title: 'Название',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Cron',
      dataIndex: 'cron_expr',
      key: 'cron_expr',
      render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code>,
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
        <Switch
          checked={v}
          size="small"
          loading={toggleMut.isPending}
          onChange={(checked) => toggleMut.mutate({ id: r.id, enabled: checked })}
        />
      ),
    },
    {
      title: '',
      key: 'actions',
      render: (_: unknown, r: SyncScheduleOut) => (
        <Space size={4}>
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
          onClick={() => setAddOpen(true)}
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
      />

      <Modal
        title="Новое расписание"
        open={addOpen}
        onCancel={() => { setAddOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
        confirmLoading={createMut.isPending}
        okText="Создать"
        cancelText="Отмена"
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => createMut.mutate(values)}
          initialValues={{ mode: 'normal', enabled: true }}
        >
          <Form.Item name="name" label="Название" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="cron_expr"
            label="Cron-выражение"
            rules={[{ required: true }]}
            extra="Пример: 0 6 * * * (каждый день в 06:00)"
          >
            <Input placeholder="0 6 * * *" />
          </Form.Item>
          <Form.Item name="mode" label="Режим" rules={[{ required: true }]}>
            <Select
              options={Object.entries(MODE_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </Form.Item>
          <Form.Item name="team" label="Команда (для режима «По команде»)">
            <Input placeholder="Оставьте пустым для других режимов" />
          </Form.Item>
          <Form.Item name="enabled" label="Включено" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
