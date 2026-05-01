import { useState } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Switch,
  InputNumber,
  Popconfirm,
  Space,
  Tag,
  App,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, LockOutlined } from '@ant-design/icons';
import {
  useMandatoryWorkTypes,
  useCreateMandatoryWorkType,
  useUpdateMandatoryWorkType,
  useDeleteMandatoryWorkType,
} from '../../hooks/useCapacity';
import type { MandatoryWorkType } from '../../types/api';

interface FormValues {
  code: string;
  label: string;
  is_active: boolean;
  sort_order: number;
  subtracts_from_pool: boolean;
}

export default function WorkTypesTab() {
  const { notification } = App.useApp();
  const { data: items = [], isLoading } = useMandatoryWorkTypes();
  const create = useCreateMandatoryWorkType();
  const update = useUpdateMandatoryWorkType();
  const remove = useDeleteMandatoryWorkType();

  const [editing, setEditing] = useState<MandatoryWorkType | null>(null);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm<FormValues>();

  const open = editing !== null || creating;
  const isSystemEditing = editing?.is_system === true;

  const openEdit = (row: MandatoryWorkType) => {
    setEditing(row);
    form.setFieldsValue({
      code: row.code,
      label: row.label,
      is_active: row.is_active,
      sort_order: row.sort_order,
      subtracts_from_pool: row.subtracts_from_pool,
    });
  };

  const openCreate = () => {
    setCreating(true);
    form.resetFields();
    form.setFieldsValue({
      is_active: true,
      subtracts_from_pool: true,
      sort_order: 0,
    });
  };

  const close = () => {
    setEditing(null);
    setCreating(false);
    form.resetFields();
  };

  const onSubmit = async () => {
    let values: FormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    try {
      if (editing) {
        const { code: _code, ...rest } = values;
        const body = editing.is_system ? rest : values;
        await update.mutateAsync({ id: editing.id, body });
      } else {
        await create.mutateAsync(values);
      }
      close();
      notification.success({ title: 'Сохранено' });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Ошибка сохранения';
      notification.error({ title: 'Ошибка', description: msg });
    }
  };

  const onDelete = async (id: string) => {
    try {
      await remove.mutateAsync(id);
      notification.success({ title: 'Удалено' });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Удаление запрещено';
      notification.error({ title: 'Ошибка', description: msg });
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          Добавить вид работ
        </Button>
      </Space>
      <Table<MandatoryWorkType>
        rowKey="id"
        loading={isLoading}
        dataSource={items}
        size="small"
        pagination={false}
        columns={[
          {
            title: 'Код',
            dataIndex: 'code',
            key: 'code',
            width: 220,
            render: (v, row) => (
              <Space>
                <code>{v}</code>
                {row.is_system && (
                  <Tag icon={<LockOutlined />} color="purple">
                    системный
                  </Tag>
                )}
              </Space>
            ),
          },
          { title: 'Название', dataIndex: 'label', key: 'label' },
          {
            title: 'Активен',
            dataIndex: 'is_active',
            key: 'is_active',
            width: 100,
            render: (v: boolean) =>
              v ? <Tag color="green">да</Tag> : <Tag>нет</Tag>,
          },
          {
            title: 'Вычитается из пула',
            dataIndex: 'subtracts_from_pool',
            key: 'subtracts_from_pool',
            width: 170,
            render: (v: boolean) =>
              v ? <Tag color="blue">да</Tag> : <Tag>нет</Tag>,
          },
          {
            title: 'Порядок',
            dataIndex: 'sort_order',
            key: 'sort_order',
            width: 90,
            align: 'right',
          },
          {
            title: '',
            key: 'actions',
            width: 100,
            render: (_, row) => (
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => openEdit(row)}
                />
                <Popconfirm
                  title="Удалить вид работ?"
                  onConfirm={() => onDelete(row.id)}
                  disabled={row.is_system}
                  okText="Удалить"
                  cancelText="Отмена"
                >
                  <Button
                    size="small"
                    icon={<DeleteOutlined />}
                    danger
                    disabled={row.is_system}
                  />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        open={open}
        forceRender
        title={editing ? `Изменить «${editing.label}»` : 'Новый вид работ'}
        onOk={onSubmit}
        onCancel={close}
        confirmLoading={create.isPending || update.isPending}
        okText="Сохранить"
        cancelText="Отмена"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="Код"
            name="code"
            rules={[{ required: true, max: 64 }]}
            tooltip={isSystemEditing ? 'Код системного вида менять нельзя' : undefined}
          >
            <Input disabled={isSystemEditing} />
          </Form.Item>
          <Form.Item
            label="Название"
            name="label"
            rules={[{ required: true, max: 255 }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="Активен" name="is_active" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            label="Вычитается из пула"
            name="subtracts_from_pool"
            valuePropName="checked"
            tooltip="Если включено — план этого вида уменьшает доступный «проектный» пул сотрудника"
          >
            <Switch />
          </Form.Item>
          <Form.Item label="Порядок" name="sort_order">
            <InputNumber min={0} max={999} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
