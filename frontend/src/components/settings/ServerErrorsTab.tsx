import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Empty, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import { ReloadOutlined, DeleteOutlined } from '@ant-design/icons';
import { serverErrorsApi } from '../../api/serverErrors';
import type { ServerErrorItem, ServerErrorList } from '../../api/serverErrors';

const { Text, Paragraph } = Typography;

// Частые причины на человеческом языке — чтобы не пересылать разработчику
// каждый случай. Незнакомый тип показываем как есть.
const PLAIN_CAUSE: Record<string, string> = {
  OperationalError: 'Сервис не смог обратиться к базе данных',
  DBAPIError: 'Сервис не смог обратиться к базе данных',
  TimeoutError: 'База данных не ответила вовремя',
  IntegrityError: 'Данные не прошли проверку целостности при записи',
};

// Отказ по паролю выглядит так же, как «база недоступна», а чинится иначе:
// это адрес или пароль базы, а не сама база.
function plainCause(row: ServerErrorItem): string {
  if (row.message.includes('password authentication failed')) {
    return 'База данных отвергла подключение сервиса — не подошёл пароль или адрес';
  }
  return PLAIN_CAUSE[row.error_type] ?? row.error_type;
}

function fmt(dt: string): string {
  return new Date(dt).toLocaleString('ru-RU');
}

export default function ServerErrorsTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();

  const list = useQuery<ServerErrorList>({
    queryKey: ['admin', 'server-errors'],
    queryFn: () => serverErrorsApi.list(),
    refetchInterval: 30000,
  });

  const clearMut = useMutation({
    mutationFn: () => serverErrorsApi.clear(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'server-errors'] });
      notification.success({ title: 'Список очищен' });
    },
    onError: () => notification.error({ title: 'Не удалось очистить список' }),
  });

  const items = list.data?.items ?? [];

  const columns = [
    {
      title: 'Когда',
      dataIndex: 'at',
      width: 180,
      render: (v: string) => fmt(v),
    },
    {
      title: 'Что случилось',
      dataIndex: 'error_type',
      render: (_: string, row: ServerErrorItem) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{plainCause(row)}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{row.message}</Text>
        </Space>
      ),
    },
    {
      title: 'Где',
      dataIndex: 'path',
      width: 320,
      render: (v: string, row: ServerErrorItem) => (
        <Text code style={{ fontSize: 12 }}>
          {row.method} {v}
        </Text>
      ),
    },
    {
      title: 'У кого',
      dataIndex: 'user',
      width: 200,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: 'Номер',
      dataIndex: 'id',
      width: 130,
      render: (v: string) => <Tag>{v}</Tag>,
    },
  ];

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        title="Последние сбои сервиса"
        description={
          <>
            <Paragraph style={{ marginBottom: 8 }}>
              Сюда попадает всё, что на экране выглядит как «что-то пошло не так».
              Разверните строку — там полная запись о сбое, её можно скопировать
              и приложить к обращению.
            </Paragraph>
            <Paragraph style={{ marginBottom: 0 }}>
              Список живёт в памяти сервиса: хранится последние {list.data?.capacity ?? 200} записей
              и очищается при перезапуске. Если список пуст, а сбои были — значит сервис
              перезапускался; время запуска показано ниже.
            </Paragraph>
          </>
        }
      />

      <Space wrap>
        <Button
          icon={<ReloadOutlined />}
          loading={list.isFetching}
          onClick={() => list.refetch()}
        >
          Обновить
        </Button>
        <Popconfirm
          title="Очистить список?"
          description="Записи о сбоях удалятся безвозвратно."
          okText="Очистить"
          cancelText="Отмена"
          onConfirm={() => clearMut.mutate()}
        >
          <Button icon={<DeleteOutlined />} danger disabled={items.length === 0}>
            Очистить
          </Button>
        </Popconfirm>
        {list.data && (
          <Text type="secondary">
            Сервис работает с {fmt(list.data.started_at)}
          </Text>
        )}
      </Space>

      <Table<ServerErrorItem>
        rowKey="id"
        size="small"
        loading={list.isLoading}
        dataSource={items}
        columns={columns}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
        locale={{
          emptyText: <Empty description="Сбоев не было" />,
        }}
        expandable={{
          expandedRowRender: (row) => (
            <Paragraph
              copyable={{ text: row.traceback }}
              style={{
                margin: 0,
                whiteSpace: 'pre-wrap',
                fontFamily: 'monospace',
                fontSize: 12,
              }}
            >
              {row.query ? `Параметры: ${row.query}\n\n` : ''}
              {row.traceback}
            </Paragraph>
          ),
        }}
      />
    </Space>
  );
}
