import { useState, useCallback } from 'react';
import { Table, Button, Space, Popconfirm, App, Modal, Form, Input, InputNumber, Select } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, HolderOutlined } from '@ant-design/icons';
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import { useBacklogItems, useCreateBacklogItem, useUpdateBacklogItem, useDeleteBacklogItem, useProjects } from '../hooks/useBacklog';
import { useQuarterYear } from '../hooks/useQuarterYear';
import { formatHours } from '../utils/format';
import type { BacklogItemResponse } from '../types/api';

function DragHandle({ id }: { id: string }) {
  const { attributes, listeners } = useSortable({ id });
  return <HolderOutlined style={{ cursor: 'grab', color: '#999' }} {...attributes} {...listeners} />;
}

function SortableRow(props: React.HTMLAttributes<HTMLTableRowElement> & { 'data-row-key'?: string }) {
  const id = props['data-row-key'] ?? '';
  const { setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <tr
      {...props}
      ref={setNodeRef}
      style={{ ...props.style, transform: CSS.Translate.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }}
    />
  );
}

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
        onSuccess: () => { setOpen(false); notification.success({ title: 'Обновлено' }); },
        onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
      });
    } else {
      create.mutate(vals as Parameters<typeof create.mutate>[0], {
        onSuccess: () => { setOpen(false); form.resetFields(); notification.success({ title: 'Создано' }); },
        onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
      });
    }
  };

  const sorted = data?.slice().sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));

  const handleDragEnd = useCallback(({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id || !sorted) return;

    const oldIndex = sorted.findIndex((i) => i.id === active.id);
    const newIndex = sorted.findIndex((i) => i.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const newPriority = newIndex + 1;
    update.mutate({ id: String(active.id), data: { priority: newPriority } });
  }, [sorted, update]);

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

      <DndContext collisionDetection={closestCenter} modifiers={[restrictToVerticalAxis]} onDragEnd={handleDragEnd}>
        <SortableContext items={sorted?.map((i) => i.id) ?? []} strategy={verticalListSortingStrategy}>
          <Table<BacklogItemResponse>
            dataSource={sorted}
            rowKey="id"
            loading={isLoading}
            pagination={false}
            size="small"
            components={{ body: { row: SortableRow } }}
            columns={[
              {
                title: '', width: 40,
                render: (_, r) => <DragHandle id={r.id} />,
              },
              { title: '#', dataIndex: 'priority', width: 60 },
              { title: 'Название', dataIndex: 'title' },
              { title: 'Проект', dataIndex: 'project_id', render: (id: string | null) => id ? (projectMap.get(id)?.key || id) : '—' },
              { title: 'Оценка (ч)', dataIndex: 'estimate_hours', render: (v: number | null) => v != null ? formatHours(v) : '—' },
              {
                title: 'Действия', width: 100,
                render: (_, r) => (
                  <Space>
                    <Button icon={<EditOutlined />} size="small" onClick={(e) => { e.stopPropagation(); openEdit(r); }} />
                    <Popconfirm title="Удалить?" onConfirm={() => del.mutate(r.id, { onError: (e) => notification.error({ title: 'Ошибка', description: e.message }) })}>
                      <Button icon={<DeleteOutlined />} size="small" danger onClick={(e) => e.stopPropagation()} />
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </SortableContext>
      </DndContext>
    </Space>
  );
}
