import { Button, Card, Table, Tag, Space, Collapse, Typography, App } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { getSyncRuns, type SyncRunOut, type StageReport } from '../../api/syncRuns';
import { formatDate } from '../../utils/format';

const { Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  ok: 'success',
  partial: 'warning',
  failed: 'error',
  cancelled: 'default',
  running: 'processing',
  skipped: 'default',
};

const STATUS_LABELS: Record<string, string> = {
  ok: 'Успешно',
  partial: 'Частично',
  failed: 'Ошибка',
  cancelled: 'Прерван',
  running: 'Выполняется',
  skipped: 'Пропущен',
};

const MODE_LABELS: Record<string, string> = {
  quick: 'Быстрый',
  normal: 'Обычный',
  full: 'Полный',
  team: 'Команда',
};

function StagesCollapse({ stages }: { stages: StageReport[] }) {
  if (!stages.length) return null;
  const items = stages.map((s) => ({
    key: s.stage,
    label: (
      <Space>
        <Tag color={STATUS_COLOR[s.status] ?? 'default'} style={{ fontSize: 11 }}>{s.status}</Tag>
        <Text style={{ fontSize: 13 }}>{s.stage}</Text>
        {s.counts && Object.keys(s.counts).length > 0 && (
          <Text type="secondary" style={{ fontSize: 11 }}>
            {Object.entries(s.counts).map(([k, v]) => `${k}: ${v}`).join(' · ')}
          </Text>
        )}
      </Space>
    ),
    children: s.error ? (
      <Text type="danger" style={{ fontSize: 12 }}>{s.error}</Text>
    ) : (
      <Text type="secondary" style={{ fontSize: 12 }}>
        {s.started} — {s.finished ?? '…'}
      </Text>
    ),
  }));
  return <Collapse size="small" ghost items={items} />;
}

export default function SyncHistory() {
  const { notification } = App.useApp();
  const { data: runs = [], isLoading, refetch } = useQuery({
    queryKey: ['sync', 'runs'],
    queryFn: () => getSyncRuns(30),
    refetchInterval: (query) => {
      // Автообновление если есть running запуск
      const rows = query.state.data as SyncRunOut[] | undefined;
      return rows?.some((r) => r.status === 'running') ? 5000 : false;
    },
  });

  const columns = [
    {
      title: 'Время',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (v: string) => formatDate(v),
    },
    {
      title: 'Режим',
      dataIndex: 'mode',
      key: 'mode',
      render: (v: string) => <Tag>{MODE_LABELS[v] ?? v}</Tag>,
    },
    {
      title: 'Команда',
      dataIndex: 'team',
      key: 'team',
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => (
        <Tag color={STATUS_COLOR[v] ?? 'default'}>{STATUS_LABELS[v] ?? v}</Tag>
      ),
    },
    {
      title: 'Источник',
      dataIndex: 'trigger',
      key: 'trigger',
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {v === 'scheduled' ? 'Авто' : 'Ручной'}
        </Text>
      ),
    },
    {
      title: 'Завершён',
      dataIndex: 'finished_at',
      key: 'finished_at',
      render: (v: string | null) => v ? formatDate(v) : <Text type="secondary">—</Text>,
    },
  ];

  const expandable = {
    expandedRowRender: (r: SyncRunOut) => (
      <Space direction="vertical" style={{ width: '100%', paddingLeft: 16 }}>
        {r.error_text && (
          <Text type="danger" style={{ fontSize: 12 }}>{r.error_text}</Text>
        )}
        <StagesCollapse stages={r.stages_json} />
      </Space>
    ),
    rowExpandable: (r: SyncRunOut) => r.stages_json.length > 0 || !!r.error_text,
  };

  const handleRefetch = async () => {
    try {
      await refetch();
    } catch (e) {
      notification.error({ message: 'Ошибка загрузки', description: (e as Error).message });
    }
  };

  return (
    <Card
      title="История запусков"
      size="small"
      extra={
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={isLoading}
          onClick={handleRefetch}
        >
          Обновить
        </Button>
      }
    >
      <Table<SyncRunOut>
        dataSource={runs}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        pagination={{ pageSize: 10, showSizeChanger: false }}
        size="small"
        expandable={expandable}
      />
    </Card>
  );
}
