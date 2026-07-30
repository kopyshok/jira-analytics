import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, App, Button, Card, Descriptions, Progress, Space, Typography,
} from 'antd';
import { CloudDownloadOutlined, DatabaseOutlined } from '@ant-design/icons';
import { dbExportApi } from '../../api/dbExport';
import type { DbExportStatus } from '../../api/dbExport';

const { Paragraph, Text } = Typography;

function formatSize(bytes: number | null): string {
  if (!bytes) return '—';
  const mb = bytes / (1024 * 1024);
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} ГБ` : `${mb.toFixed(1)} МБ`;
}

export default function DbExportTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();

  const status = useQuery<DbExportStatus>({
    queryKey: ['admin', 'db-export'],
    queryFn: () => dbExportApi.status(),
    refetchInterval: (query) =>
      query.state.data?.state === 'running' ? 2000 : false,
  });

  const startMut = useMutation({
    mutationFn: () => dbExportApi.start(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'db-export'] });
      notification.info({
        title: 'Выгрузка запущена',
        description: 'Сборка файла занимает несколько минут — прогресс обновляется сам.',
      });
    },
    onError: () => notification.error({ title: 'Не удалось запустить выгрузку' }),
  });

  const downloadMut = useMutation({
    mutationFn: (fileName: string) => dbExportApi.download(fileName),
    onError: () => notification.error({ title: 'Не удалось скачать файл' }),
  });

  const data = status.data;
  const running = data?.state === 'running';
  const ready = data?.state === 'done' && !!data.file_name;
  const percent = data && data.tables_total
    ? Math.round((data.tables_done / data.tables_total) * 100)
    : 0;

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%', maxWidth: 900 }}>
      <Alert
        type="info"
        showIcon
        title="Копия базы для локальной работы"
        description={
          <>
            <Paragraph style={{ marginBottom: 8 }}>
              Сервис соберёт файл со всеми данными — командами, сотрудниками, задачами,
              бэклогом, сценариями и настройками. Файл кладётся в папку данных локального
              сервиса вместо текущей базы, после чего локальная копия повторяет продуктив.
            </Paragraph>
            <Paragraph style={{ marginBottom: 0 }}>
              Пароли и ключи доступа к Jira в файл не попадают: для локального входа
              выдаётся общий временный пароль, ключи вводятся заново.
            </Paragraph>
          </>
        }
      />

      <Card>
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Button
              type="primary"
              icon={<DatabaseOutlined />}
              loading={running || startMut.isPending}
              onClick={() => startMut.mutate()}
            >
              {running ? 'Собираем…' : 'Собрать выгрузку'}
            </Button>
            <Button
              icon={<CloudDownloadOutlined />}
              disabled={!ready}
              loading={downloadMut.isPending}
              onClick={() => data?.file_name && downloadMut.mutate(data.file_name)}
            >
              Скачать файл
            </Button>
          </Space>

          {running && (
            <Progress
              percent={percent}
              status="active"
              format={() => `${data?.tables_done ?? 0} / ${data?.tables_total ?? 0}`}
            />
          )}

          {data?.state === 'error' && (
            <Alert type="error" showIcon title="Выгрузка не удалась" description={data.error} />
          )}

          {ready && data && (
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Файл">{data.file_name}</Descriptions.Item>
              <Descriptions.Item label="Размер">{formatSize(data.file_size)}</Descriptions.Item>
              <Descriptions.Item label="Перенесено записей">
                {data.rows_copied.toLocaleString('ru-RU')}
              </Descriptions.Item>
              <Descriptions.Item label="Локальный пароль для входа">
                <Text copyable strong>{data.local_password}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Собран">
                {data.finished_at
                  ? new Date(data.finished_at).toLocaleString('ru-RU')
                  : '—'}
              </Descriptions.Item>
            </Descriptions>
          )}

          {ready && (
            <Alert
              type="warning"
              showIcon
              title="Локальная база будет заменена целиком"
              description={
                <>
                  Файл распаковывается и кладётся на место локальной базы — всё, что было
                  в локальной копии, пропадёт. Вход в локальный сервис — под своей почтой
                  и временным паролем выше. Ссылка на скачивание живёт сутки.
                </>
              }
            />
          )}
        </Space>
      </Card>
    </Space>
  );
}
