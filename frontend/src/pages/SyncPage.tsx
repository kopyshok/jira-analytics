import { useState } from 'react';
import { Button, Card, Space, Table, Tag, App, Descriptions } from 'antd';
import { SyncOutlined, ApiOutlined, ReloadOutlined } from '@ant-design/icons';
import { testConnection } from '../api/sync';
import { useSyncStatus, useSyncMutation, useRecalculateMapping } from '../hooks/useSync';
import { formatDate } from '../utils/format';
import type { ConnectionTestResponse, SyncStatusResponse } from '../types/api';

export default function SyncPage() {
  const { message, notification } = App.useApp();
  const [conn, setConn] = useState<ConnectionTestResponse | null>(null);
  const [testing, setTesting] = useState(false);
  const { data: statuses, isLoading } = useSyncStatus();
  const recalculate = useRecalculateMapping();

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await testConnection();
      setConn(res);
      if (res.connected) message.success('Подключение успешно');
      else message.error(res.error || 'Не удалось подключиться');
    } catch (e: unknown) {
      message.error((e as Error).message);
    } finally {
      setTesting(false);
    }
  };

  const SyncButton = ({ type, label }: { type: 'projects' | 'issues' | 'worklogs' | 'comments' | 'full'; label: string }) => {
    const mutation = useSyncMutation(type);
    return (
      <Button
        icon={<SyncOutlined spin={mutation.isPending} />}
        loading={mutation.isPending}
        onClick={() => mutation.mutate(undefined, {
          onSuccess: (res) => notification.success({ message: label, description: res.message }),
          onError: (e) => notification.error({ message: `Ошибка: ${label}`, description: e.message }),
        })}
      >
        {label}
      </Button>
    );
  };

  const columns = [
    { title: 'Сущность', dataIndex: 'entity', key: 'entity' },
    {
      title: 'Последняя синхронизация',
      dataIndex: 'last_sync',
      key: 'last_sync',
      render: (v: string | null) => formatDate(v),
    },
    {
      title: 'Ошибка',
      dataIndex: 'last_error',
      key: 'last_error',
      render: (v: string | null) => v ? <Tag color="red">{v}</Tag> : <Tag color="green">OK</Tag>,
    },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="Подключение к Jira">
        <Space direction="vertical">
          <Button icon={<ApiOutlined />} onClick={handleTest} loading={testing}>
            Проверить подключение
          </Button>
          {conn && conn.connected && (
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="Пользователь">{conn.user_name}</Descriptions.Item>
              <Descriptions.Item label="Email">{conn.user_email}</Descriptions.Item>
            </Descriptions>
          )}
        </Space>
      </Card>

      <Card title="Синхронизация">
        <Space wrap>
          <SyncButton type="projects" label="Проекты" />
          <SyncButton type="issues" label="Задачи" />
          <SyncButton type="worklogs" label="Ворклоги" />
          <SyncButton type="comments" label="Комментарии" />
          <SyncButton type="full" label="Полная синхронизация" />
        </Space>
      </Card>

      <Card
        title="Статус синхронизации"
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={() => recalculate.mutate(undefined, {
              onSuccess: (res) => notification.success({ message: 'Маппинг', description: res.message }),
              onError: (e) => notification.error({ message: 'Ошибка маппинга', description: e.message }),
            })}
            loading={recalculate.isPending}
          >
            Пересчитать маппинг
          </Button>
        }
      >
        <Table<SyncStatusResponse>
          dataSource={statuses}
          columns={columns}
          rowKey="entity"
          loading={isLoading}
          pagination={false}
          size="small"
        />
      </Card>
    </Space>
  );
}
