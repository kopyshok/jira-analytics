import { useState, useCallback } from 'react';
import {
  Space, Table, Select, Input, App, Tag, Button, Popconfirm, ColorPicker, Modal, Form,
} from 'antd';
import { LockOutlined, DeleteOutlined, PlusOutlined, HolderOutlined } from '@ant-design/icons';
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import type { AggregationColor } from 'antd/es/color-picker/color';
import {
  useCategories, useUpdateCategory, useDeleteCategory, useCreateCategory,
} from '../hooks/useCategories';
import { useMandatoryWorkTypes } from '../hooks/useCapacity';
import type { CategoryResponse } from '../types/api';

function DragHandle({ id }: { id: string }) {
  const { attributes, listeners } = useSortable({ id });
  return (
    <HolderOutlined
      style={{ cursor: 'grab', color: '#8faec8' }}
      {...attributes}
      {...listeners}
    />
  );
}

function SortableRow(props: React.HTMLAttributes<HTMLTableRowElement> & { 'data-row-key'?: string }) {
  const id = props['data-row-key'] ?? '';
  const { setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <tr
      {...props}
      ref={setNodeRef}
      style={{
        ...props.style,
        transform: CSS.Translate.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
      }}
    />
  );
}

export default function CategoriesTab() {
  const { notification } = App.useApp();
  const { items, isLoading } = useCategories();
  const update = useUpdateCategory();
  const del = useDeleteCategory();
  const create = useCreateCategory();
  const wts = useMandatoryWorkTypes({ isActive: true });

  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm<{ label: string; color: string }>();

  const wtOptions = [
    { value: '', label: '— Без привязки —' },
    ...(wts.data ?? []).map(w => ({ value: w.id, label: w.label })),
  ];

  const handleDragEnd = useCallback(
    ({ active: draggingActive, over }: DragEndEvent) => {
      if (!over || draggingActive.id === over.id) return;
      const oldIndex = items.findIndex(i => i.id === draggingActive.id);
      const newIndex = items.findIndex(i => i.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;

      // Reorder: assign sort_order = index position for affected items
      const reordered = [...items];
      const [moved] = reordered.splice(oldIndex, 1);
      reordered.splice(newIndex, 0, moved);

      reordered.forEach((item, idx) => {
        if (item.sort_order !== idx) {
          update.mutate(
            { id: item.id, body: { sort_order: idx } },
            { onError: (err) => notification.error({ title: 'Ошибка', description: err.message }) },
          );
        }
      });
    },
    [items, update, notification],
  );

  const handleAddSubmit = (vals: { label: string; color: string }) => {
    const label = vals.label.trim();
    const code = label.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
    const color = vals.color || undefined;
    create.mutate(
      { code, label, color },
      {
        onSuccess: () => {
          setAddOpen(false);
          form.resetFields();
          notification.success({ title: 'Категория добавлена' });
        },
        onError: (err) => notification.error({ title: 'Ошибка', description: err.message }),
      },
    );
  };

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <DndContext
        collisionDetection={closestCenter}
        modifiers={[restrictToVerticalAxis]}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={items.map(i => i.id)} strategy={verticalListSortingStrategy}>
          <Table<CategoryResponse>
            dataSource={items}
            rowKey="id"
            loading={isLoading}
            pagination={false}
            size="small"
            components={{ body: { row: SortableRow } }}
            columns={[
              {
                title: '',
                width: 36,
                render: (_: unknown, r: CategoryResponse) => <DragHandle id={r.id} />,
              },
              { title: 'Code', dataIndex: 'code', width: 180 },
              {
                title: 'Название', dataIndex: 'label',
                render: (v: string, r: CategoryResponse) => (
                  <Input
                    size="small"
                    defaultValue={v}
                    key={v}
                    onBlur={(e) => {
                      const val = e.currentTarget.value.trim();
                      if (val && val !== v) {
                        update.mutate(
                          { id: r.id, body: { label: val } },
                          { onError: (err) => notification.error({ title: 'Ошибка', description: err.message }) },
                        );
                      }
                    }}
                  />
                ),
              },
              {
                title: 'Цвет', dataIndex: 'color', width: 80,
                render: (v: string | null, r: CategoryResponse) => (
                  <ColorPicker
                    size="small"
                    value={v ?? '#ffffff'}
                    onChange={(color: AggregationColor) => {
                      const hex = color.toHexString();
                      if (hex !== (v ?? '#ffffff')) {
                        update.mutate(
                          { id: r.id, body: { color: hex } },
                          { onError: (err) => notification.error({ title: 'Ошибка', description: err.message }) },
                        );
                      }
                    }}
                  />
                ),
              },
              {
                title: 'Вид работ', dataIndex: 'work_type_id', width: 240,
                render: (v: string | null, r: CategoryResponse) => (
                  <Select
                    size="small"
                    style={{ width: '100%' }}
                    value={v ?? ''}
                    options={wtOptions}
                    onChange={(next: string) => {
                      update.mutate(
                        { id: r.id, body: { work_type_id: next || null } },
                        { onError: (err) => notification.error({ title: 'Ошибка', description: err.message }) },
                      );
                    }}
                  />
                ),
              },
              {
                title: 'Системная', dataIndex: 'is_system', width: 100,
                render: (v: boolean) => v ? <Tag color="blue">да</Tag> : null,
              },
              {
                title: '',
                width: 50,
                render: (_: unknown, r: CategoryResponse) =>
                  r.is_system ? (
                    <LockOutlined style={{ color: '#8faec8' }} />
                  ) : (
                    <Popconfirm
                      title="Удалить категорию?"
                      okText="Удалить"
                      cancelText="Отмена"
                      okButtonProps={{ danger: true }}
                      onConfirm={() =>
                        del.mutate(r.id, {
                          onSuccess: () => notification.success({ title: 'Категория удалена' }),
                          onError: (err) => notification.error({ title: 'Ошибка', description: err.message }),
                        })
                      }
                    >
                      <Button icon={<DeleteOutlined />} size="small" danger />
                    </Popconfirm>
                  ),
              },
            ]}
          />
        </SortableContext>
      </DndContext>

      <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
        Добавить категорию
      </Button>

      <Modal
        title="Добавить категорию"
        open={addOpen}
        onCancel={() => { setAddOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
        okText="Добавить"
        cancelText="Отмена"
      >
        <Form form={form} layout="vertical" onFinish={handleAddSubmit}>
          <Form.Item name="label" label="Название" rules={[{ required: true, message: 'Введите название' }]}>
            <Input placeholder="напр. Тестирование" />
          </Form.Item>
          <Form.Item name="color" label="Цвет" initialValue="#8c8c8c">
            <Input placeholder="#rrggbb" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
