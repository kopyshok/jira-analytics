import { useState } from 'react';
import {
  Space, Button, Table, Tag, Switch, Input, Modal, Form, Popconfirm, App,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons';
import {
  useRoles, useCreateRole, usePatchRole, useDeleteRole, useReorderRoles,
} from '../../hooks/useRoles';
import type { Role } from '../../types/api';

export default function RolesTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useRoles();
  const create = useCreateRole();
  const patch = usePatchRole();
  const del = useDeleteRole();
  const reorder = useReorderRoles();

  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const rows = [...(data ?? [])].sort((a, b) => a.sort_order - b.sort_order);

  const swap = (idx: number, dir: -1 | 1) => {
    const j = idx + dir;
    if (j < 0 || j >= rows.length) return;
    const next = [...rows];
    [next[idx], next[j]] = [next[j], next[idx]];
    reorder.mutate(next.map(x => x.id));
  };

  const columns = [
    {
      title: '↕', width: 80,
      render: (_: unknown, _r: Role, idx: number) => (
        <Space size={4}>
          <Button size="small" icon={<ArrowUpOutlined />} disabled={idx === 0}
            onClick={() => swap(idx, -1)} />
          <Button size="small" icon={<ArrowDownOutlined />} disabled={idx === rows.length - 1}
            onClick={() => swap(idx, 1)} />
        </Space>
      ),
    },
    {
      title: 'Code', dataIndex: 'code', width: 140,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    { title: 'Название', dataIndex: 'label' },
    {
      title: 'Цвет', dataIndex: 'color', width: 140,
      render: (v: string, r: Role) => (
        <Input
          size="small"
          defaultValue={v ?? ''}
          style={{ width: 110 }}
          onBlur={(e) => {
            const val = e.currentTarget.value.trim() || '#8c8c8c';
            if (val === v) return;
            patch.mutate({ id: r.id, body: { color: val } }, {
              onError: (e2) => notification.error({ title: 'Ошибка', description: e2.message }),
            });
          }}
        />
      ),
    },
    {
      title: 'В планировании', dataIndex: 'counts_in_planning', width: 130,
      render: (v: boolean, r: Role) => (
        <Switch checked={v} onChange={(next) => patch.mutate(
          { id: r.id, body: { counts_in_planning: next } },
          { onError: (e) => notification.error({ title: 'Ошибка', description: e.message }) },
        )} />
      ),
    },
    {
      title: 'Активна', dataIndex: 'is_active', width: 90,
      render: (v: boolean, r: Role) => (
        <Switch checked={v} onChange={(next) => patch.mutate(
          { id: r.id, body: { is_active: next } },
          { onError: (e) => notification.error({ title: 'Ошибка', description: e.message }) },
        )} />
      ),
    },
    {
      title: '', width: 50,
      render: (_: unknown, r: Role) => (
        <Popconfirm
          title="Удалить роль?"
          description="Если у сотрудников есть эта роль — сначала переназначьте их."
          okText="Удалить"
          cancelText="Отмена"
          okButtonProps={{ danger: true }}
          onConfirm={() => del.mutate(r.id, {
            onSuccess: () => notification.success({ title: 'Удалено' }),
            onError: (e) => {
              const detail = (e as { detail?: string }).detail ?? e.message;
              notification.error({ title: 'Нельзя удалить', description: detail });
            },
          })}
        >
          <Tag style={{ cursor: 'pointer' }} color="red" icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} type="primary" onClick={() => {
        form.resetFields();
        setOpen(true);
      }}>Добавить роль</Button>

      <Modal
        title="Новая роль"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => {
          create.mutate({
            code: v.code,
            label: v.label,
            color: v.color || '#8c8c8c',
            is_active: true,
            counts_in_planning: v.counts_in_planning ?? true,
            sort_order: rows.length,
          }, {
            onSuccess: () => {
              setOpen(false);
              notification.success({ title: 'Роль добавлена' });
            },
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          });
        }}>
          <Form.Item name="code" label="Code" rules={[{ required: true }]}>
            <Input placeholder="напр. analyst" />
          </Form.Item>
          <Form.Item name="label" label="Название" rules={[{ required: true }]}>
            <Input placeholder="напр. Аналитик" />
          </Form.Item>
          <Form.Item name="color" label="Цвет (hex)" initialValue="#8c8c8c">
            <Input placeholder="#rrggbb" />
          </Form.Item>
          <Form.Item name="counts_in_planning" label="Участвует в планировании" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Table<Role>
        dataSource={rows}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={columns}
      />
    </Space>
  );
}
