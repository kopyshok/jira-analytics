import { EditOutlined, KeyOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, Modal, Select, Space, Switch, Table, notification } from 'antd';
import { useEffect, useState } from 'react';
import {
  createUser, listUsers, resetPassword, updateUser,
  type UserCreate, type UserUpdate,
} from '../../api/adminUsers';
import type { UserProfile } from '../../api/auth';

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Администратор' },
  { value: 'super_manager', label: 'Руководитель (все команды)' },
  { value: 'manager', label: 'Руководитель' },
];
const ROLE_LABEL: Record<string, string> = Object.fromEntries(
  ROLE_OPTIONS.map((o) => [o.value, o.label]),
);

export default function UsersTab() {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editUser, setEditUser] = useState<UserProfile | null>(null);
  const [resetUser, setResetUser] = useState<UserProfile | null>(null);
  const [form] = Form.useForm();
  const [resetForm] = Form.useForm();

  function refresh() {
    setLoading(true);
    listUsers().then(setUsers).finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleCreate(values: UserCreate) {
    try {
      await createUser(values);
      refresh();
      setCreateOpen(false);
      form.resetFields();
      notification.success({ message: 'Пользователь создан' });
    } catch {
      notification.error({ message: 'Ошибка при создании' });
    }
  }

  async function handleUpdate(values: UserUpdate) {
    if (!editUser) return;
    try {
      await updateUser(editUser.id, values);
      refresh();
      setEditUser(null);
      notification.success({ message: 'Изменения сохранены' });
    } catch {
      notification.error({ message: 'Ошибка при сохранении' });
    }
  }

  async function handleToggleActive(user: UserProfile) {
    try {
      await updateUser(user.id, { is_active: !user.is_active });
      refresh();
    } catch {
      notification.error({ message: 'Ошибка' });
    }
  }

  async function handleResetPassword(values: { new_password: string }) {
    if (!resetUser) return;
    try {
      await resetPassword(resetUser.id, values.new_password);
      setResetUser(null);
      resetForm.resetFields();
      notification.success({ message: 'Пароль изменён' });
    } catch {
      notification.error({ message: 'Ошибка при сбросе пароля' });
    }
  }

  const columns = [
    { title: 'Имя', dataIndex: 'display_name', key: 'display_name' },
    { title: 'Email', dataIndex: 'email', key: 'email' },
    {
      title: 'Роль', dataIndex: 'role', key: 'role',
      render: (r: string) => ROLE_LABEL[r] ?? r,
    },
    {
      title: 'Команда', dataIndex: 'default_team', key: 'default_team',
      render: (t: string | null) => t ?? <span style={{ color: '#666' }}>—</span>,
    },
    {
      title: 'Активен', dataIndex: 'is_active', key: 'is_active',
      render: (active: boolean, u: UserProfile) => (
        <Switch checked={active} onChange={() => handleToggleActive(u)} />
      ),
    },
    {
      title: '', key: 'actions',
      render: (_: unknown, u: UserProfile) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditUser(u);
            form.setFieldsValue({ display_name: u.display_name, role: u.role, default_team: u.default_team });
          }} />
          <Button size="small" icon={<KeyOutlined />} onClick={() => setResetUser(u)} />
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          Добавить пользователя
        </Button>
      </div>
      <Table dataSource={users} columns={columns} rowKey="id" loading={loading} size="small" />

      <Modal title="Новый пользователь" open={createOpen}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        onOk={() => form.submit()} okText="Создать">
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="display_name" label="Имя" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="email" label="Email" rules={[{ required: true }]}><Input type="email" /></Form.Item>
          <Form.Item name="password" label="Пароль" rules={[{ required: true, min: 8 }]}><Input.Password /></Form.Item>
          <Form.Item name="role" label="Роль" rules={[{ required: true }]}><Select options={ROLE_OPTIONS} /></Form.Item>
          <Form.Item name="default_team" label="Команда по умолчанию">
            <Input placeholder="Пусто для admin/super_manager" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="Редактировать" open={!!editUser}
        onCancel={() => setEditUser(null)} onOk={() => form.submit()} okText="Сохранить">
        <Form form={form} layout="vertical" onFinish={handleUpdate}>
          <Form.Item name="display_name" label="Имя"><Input /></Form.Item>
          <Form.Item name="role" label="Роль"><Select options={ROLE_OPTIONS} /></Form.Item>
          <Form.Item name="default_team" label="Команда"><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal title={`Сбросить пароль — ${resetUser?.display_name}`} open={!!resetUser}
        onCancel={() => { setResetUser(null); resetForm.resetFields(); }}
        onOk={() => resetForm.submit()} okText="Сохранить">
        <Form form={resetForm} layout="vertical" onFinish={handleResetPassword}>
          <Form.Item name="new_password" label="Новый пароль" rules={[{ required: true, min: 8 }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
