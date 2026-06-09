import { useState, useCallback } from 'react';
import {
  Space, Table, Select, Input, App, Tag, Button, Popconfirm, ColorPicker, Modal, Form,
} from 'antd';
import { LockOutlined, DeleteOutlined, PlusOutlined, HolderOutlined, ReloadOutlined } from '@ant-design/icons';
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, arrayMove, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import type { AggregationColor } from 'antd/es/color-picker/color';
import { useQueryClient } from '@tanstack/react-query';
import {
  useCategories, useUpdateCategory, useDeleteCategory, useCreateCategory,
} from '../hooks/useCategories';
import { updateCategory } from '../api/categories';
import { useMandatoryWorkTypes } from '../hooks/useCapacity';
import { useRecalculateMapping } from '../hooks/useSync';
import { slugifyCode } from '../utils/slugify';
import type { CategoryResponse } from '../types/api';

function DragHandle({ id }: { id: string }) {
  const { attributes, listeners } = useSortable({ id });
  return (
    <HolderOutlined
      style={{ cursor: 'grab', color: 'var(--text-muted, #8faec8)' }}
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
  const qc = useQueryClient();
  const { items, isLoading } = useCategories();
  const update = useUpdateCategory();
  const del = useDeleteCategory();
  const create = useCreateCategory();
  const wts = useMandatoryWorkTypes({ isActive: true });
  const recalculate = useRecalculateMapping();

  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm<{ label: string; code?: string; color: string }>();

  const wtOptions = [
    { value: '', label: '— Без привязки —' },
    ...(wts.data ?? []).map(w => ({ value: w.id, label: w.label })),
  ];

  const handleDragEnd = useCallback(
    async ({ active: draggingActive, over }: DragEndEvent) => {
      if (!over || draggingActive.id === over.id || !items) return;

      const oldIndex = items.findIndex(i => i.id === draggingActive.id);
      const newIndex = items.findIndex(i => i.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;

      const reordered = arrayMove(items, oldIndex, newIndex);
      const toUpdate = reordered
        .map((item, idx) => ({ item, idx }))
        .filter(({ item, idx }) => item.sort_order !== idx);

      if (toUpdate.length === 0) return;

      try {
        await Promise.all(
          toUpdate.map(({ item, idx }) => updateCategory(item.id, { sort_order: idx })),
        );
        qc.invalidateQueries({ queryKey: ['categories'] });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Неизвестная ошибка';
        notification.error({ title: 'Ошибка сортировки', description: msg });
      }
    },
    [items, qc, notification],
  );

  const handleAddSubmit = (vals: { label: string; code?: string; color: string }) => {
    const label = vals.label.trim();
    const manualCode = (vals.code ?? '').trim();
    const code = manualCode ? slugifyCode(manualCode) : slugifyCode(label);
    if (!code) {
      notification.error({
        title: 'Не удалось сформировать код',
        description: 'Введите код вручную (латиница, цифры, подчёркивание).',
      });
      return;
    }
    if (manualCode && code !== manualCode) {
      notification.warning({
        title: 'Код нормализован',
        description: `Использован «${code}» — допустимы только a-z, 0-9, _.`,
      });
    }
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
    <Space orientation="vertical" style={{ width: '100%' }}>
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
                    onChangeComplete={(color: AggregationColor) => {
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
                    <LockOutlined style={{ color: 'var(--text-muted, #8faec8)' }} />
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

      <Space wrap>
        <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
          Добавить категорию
        </Button>
        <Button
          icon={<ReloadOutlined />}
          loading={recalculate.isPending}
          onClick={() =>
            recalculate.mutate(undefined, {
              onSuccess: (res) =>
                notification.success({ title: 'Маппинг пересчитан', description: res.message }),
              onError: (e) =>
                notification.error({ title: 'Ошибка маппинга', description: e.message }),
            })
          }
        >
          Пересчитать маппинг по задачам
        </Button>
      </Space>

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
          <Form.Item
            name="code"
            label="Код"
            tooltip="Латиница, цифры, подчёркивание. Пусто — сгенерируется из названия (с транслитерацией кириллицы)."
          >
            <Input placeholder="авто из названия" />
          </Form.Item>
          <Form.Item name="color" label="Цвет" initialValue="#8c8c8c" getValueFromEvent={(_, hex: string) => hex}>
            <ColorPicker />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
