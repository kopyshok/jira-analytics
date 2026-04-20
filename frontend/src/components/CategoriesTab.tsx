import { Space, Table, Select, Input, App, Tag } from 'antd';
import {
  useCategories, useUpdateCategory,
} from '../hooks/useCategories';
import { useMandatoryWorkTypes } from '../hooks/useCapacity';
import type { CategoryResponse } from '../types/api';

export default function CategoriesTab() {
  const { notification } = App.useApp();
  const { items, isLoading } = useCategories();
  const update = useUpdateCategory();
  const wts = useMandatoryWorkTypes({ isActive: true });

  const wtOptions = [
    { value: '', label: '— Без привязки —' },
    ...(wts.data ?? []).map(w => ({ value: w.id, label: w.label })),
  ];

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Table<CategoryResponse>
        dataSource={items}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Code', dataIndex: 'code', width: 180 },
          {
            title: 'Название', dataIndex: 'label',
            render: (v: string, r: CategoryResponse) => (
              <Input size="small" defaultValue={v}
                onBlur={(e) => {
                  const val = e.currentTarget.value.trim();
                  if (val && val !== v) {
                    update.mutate({ id: r.id, body: { label: val } }, {
                      onError: (err) => notification.error({ title: 'Ошибка', description: err.message }),
                    });
                  }
                }}
              />
            ),
          },
          {
            title: 'Цвет', dataIndex: 'color', width: 120,
            render: (v: string | null, r: CategoryResponse) => (
              <Input size="small" defaultValue={v ?? ''} style={{ width: 100 }}
                onBlur={(e) => {
                  const val = e.currentTarget.value.trim() || null;
                  if (val !== v) {
                    update.mutate({ id: r.id, body: { color: val } }, {
                      onError: (err) => notification.error({ title: 'Ошибка', description: err.message }),
                    });
                  }
                }}
              />
            ),
          },
          {
            title: 'Вид работ', dataIndex: 'work_type_id', width: 240,
            render: (v: string | null, r: CategoryResponse) => (
              <Select
                size="small" style={{ width: '100%' }}
                value={v ?? ''}
                options={wtOptions}
                onChange={(next: string) => {
                  update.mutate(
                    { id: r.id, body: { work_type_id: next || null } },
                    {
                      onError: (err) =>
                        notification.error({ title: 'Ошибка', description: err.message }),
                    },
                  );
                }}
              />
            ),
          },
          {
            title: 'Системная', dataIndex: 'is_system', width: 100,
            render: (v: boolean) => v ? <Tag color="blue">да</Tag> : null,
          },
        ]}
      />
    </Space>
  );
}
