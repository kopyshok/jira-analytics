import { useState } from 'react';
import {
  Space, Button, Table, Tag, Switch, Input, Modal, Form, Popconfirm, App,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons';
import {
  useAbsenceReasons, useCreateAbsenceReason, useUpdateAbsenceReason,
  useDeleteAbsenceReason, useReorderAbsenceReasons,
} from '../hooks/useAbsenceReasons';
import type { AbsenceReason } from '../types/api';

export default function AbsenceReasonsTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useAbsenceReasons();
  const create = useCreateAbsenceReason();
  const update = useUpdateAbsenceReason();
  const remove = useDeleteAbsenceReason();
  const reorder = useReorderAbsenceReasons();

  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const rows = data ?? [];
  const swap = (idx: number, dir: -1 | 1) => {
    const next = [...rows];
    const j = idx + dir;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    reorder.mutate(next.map(x => x.id));
  };

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} type="primary" onClick={() => {
        form.resetFields();
        setOpen(true);
      }}>Добавить причину</Button>
      <Modal
        title="Новая причина"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => {
          create.mutate({
            code: v.code, label: v.label,
            is_planned: v.is_planned ?? false,
            color: v.color || null,
            is_active: true, sort_order: rows.length,
          }, {
            onSuccess: () => { setOpen(false); notification.success({ title: 'Добавлено' }); },
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          });
        }}>
          <Form.Item name="code" label="Code" rules={[{ required: true }]}>
            <Input placeholder="напр. maternity" />
          </Form.Item>
          <Form.Item name="label" label="Название" rules={[{ required: true }]}>
            <Input placeholder="напр. Декрет" />
          </Form.Item>
          <Form.Item name="is_planned" label="Плановое" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="color" label="Цвет (hex)" initialValue="#8c8c8c">
            <Input placeholder="#rrggbb" />
          </Form.Item>
        </Form>
      </Modal>
      <Table<AbsenceReason>
        dataSource={rows}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          {
            title: '↕', width: 80,
            render: (_: unknown, _r: AbsenceReason, idx: number) => (
              <Space size={4}>
                <Button size="small" icon={<ArrowUpOutlined />} disabled={idx === 0}
                  onClick={() => swap(idx, -1)} />
                <Button size="small" icon={<ArrowDownOutlined />} disabled={idx === rows.length - 1}
                  onClick={() => swap(idx, 1)} />
              </Space>
            ),
          },
          { title: 'Code', dataIndex: 'code', width: 140 },
          { title: 'Название', dataIndex: 'label' },
          {
            title: 'Плановое', dataIndex: 'is_planned', width: 100,
            render: (v: boolean, r: AbsenceReason) => (
              <Switch checked={v} onChange={(next) => update.mutate(
                { id: r.id, body: { is_planned: next } },
                { onError: (e) => notification.error({ title: 'Ошибка', description: e.message }) },
              )} />
            ),
          },
          {
            title: 'Цвет', dataIndex: 'color', width: 140,
            render: (v: string | null, r: AbsenceReason) => (
              <Input size="small" defaultValue={v ?? ''} style={{ width: 110 }}
                onBlur={(e) => {
                  const val = e.currentTarget.value.trim() || null;
                  if (val === v) return;
                  update.mutate({ id: r.id, body: { color: val } });
                }}
              />
            ),
          },
          {
            title: 'Активен', dataIndex: 'is_active', width: 90,
            render: (v: boolean, r: AbsenceReason) => (
              <Switch checked={v} onChange={(next) => update.mutate(
                { id: r.id, body: { is_active: next } },
                { onError: (e) => notification.error({ title: 'Ошибка', description: e.message }) },
              )} />
            ),
          },
          {
            title: '', width: 50,
            render: (_: unknown, r: AbsenceReason) => (
              <Popconfirm
                title="Удалить причину?"
                description="Если есть записи с этой причиной — сначала перепривяжите их."
                onConfirm={() => remove.mutate(r.id, {
                  onSuccess: () => notification.success({ title: 'Удалено' }),
                  onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
                })}
              >
                <Tag style={{ cursor: 'pointer' }} color="red" icon={<DeleteOutlined />} />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}
