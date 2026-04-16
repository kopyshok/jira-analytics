import { useState } from 'react';
import { Table, Button, Space, Popconfirm, App, Modal, Form, Input, InputNumber, Select } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import { useBacklogItems, useCreateBacklogItem, useUpdateBacklogItem, useDeleteBacklogItem, useProjects } from '../hooks/useBacklog';
import { useQuarterYear } from '../hooks/useQuarterYear';
import { formatHours } from '../utils/format';
import type { BacklogItemResponse } from '../types/api';

export default function BacklogPage() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useBacklogItems(year, `Q${quarter}`);
  const { data: projects } = useProjects();
  const create = useCreateBacklogItem();
  const update = useUpdateBacklogItem();
  const del = useDeleteBacklogItem();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<BacklogItemResponse | null>(null);
  const [form] = Form.useForm();

  const projectMap = new Map(projects?.map((p) => [p.id, p]));

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ year: Number(year), quarter: `Q${quarter}` });
    setOpen(true);
  };

  const openEdit = (item: BacklogItemResponse) => {
    setEditing(item);
    form.setFieldsValue(item);
    setOpen(true);
  };

  const handleSubmit = (vals: Record<string, unknown>) => {
    if (editing) {
      update.mutate({ id: editing.id, data: vals }, {
        onSuccess: () => { setOpen(false); notification.success({ message: 'Обновлено' }); },
        onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
      });
    } else {
      create.mutate(vals as Parameters<typeof create.mutate>[0], {
        onSuccess: () => { setOpen(false); form.resetFields(); notification.success({ message: 'Создано' }); },
        onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
      });
    }
  };

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Space>
        <QuarterYearSelect />
        <Button icon={<PlusOutlined />} type="primary" onClick={openCreate}>Добавить</Button>
      </Space>

      <Modal title={editing ? 'Редактирование' : 'Новый элемент'} open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={create.isPending || update.isPending}>
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="title" label="Название" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="project_id" label="Проект">
            <Select allowClear showSearch optionFilterProp="label" options={projects?.map((p) => ({ value: p.id, label: `${p.key} — ${p.name}` }))} />
          </Form.Item>
          <Form.Item name="estimate_hours" label="Оценка (часы)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="priority" label="Приоритет">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="year" label="Год">
            <InputNumber min={2020} max={2030} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="quarter" label="Квартал">
            <Select options={[{ value: 'Q1' }, { value: 'Q2' }, { value: 'Q3' }, { value: 'Q4' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Table<BacklogItemResponse>
        dataSource={data}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: '#', dataIndex: 'priority', width: 60, sorter: (a, b) => (a.priority ?? 999) - (b.priority ?? 999) },
          { title: 'Название', dataIndex: 'title' },
          { title: 'Проект', dataIndex: 'project_id', render: (id: string | null) => id ? (projectMap.get(id)?.key || id) : '—' },
          { title: 'Оценка (ч)', dataIndex: 'estimate_hours', render: (v: number | null) => v != null ? formatHours(v) : '—' },
          {
            title: 'Действия', width: 100,
            render: (_, r) => (
              <Space>
                <Button icon={<EditOutlined />} size="small" onClick={() => openEdit(r)} />
                <Popconfirm title="Удалить?" onConfirm={() => del.mutate(r.id, { onError: (e) => notification.error({ message: 'Ошибка', description: e.message }) })}>
                  <Button icon={<DeleteOutlined />} size="small" danger />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
    </Space>
  );
}
