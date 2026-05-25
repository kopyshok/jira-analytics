import { Drawer, Descriptions, Typography, Tag, Empty, Space, Button } from 'antd';
import { BASE_URL } from '../../api/client';
import type { FeedbackItem } from '../../api/feedback';

interface Props {
  item: FeedbackItem | null;
  onClose: () => void;
}

interface ConsoleErrorEntry {
  message?: unknown;
}

interface NetworkErrorEntry {
  method?: unknown;
  url?: unknown;
  status?: unknown;
}

export default function FeedbackDetailDrawer({ item, onClose }: Props) {
  if (!item) {
    return <Drawer open={false} onClose={onClose} />;
  }

  const ctx = (item.context ?? {}) as Record<string, unknown>;
  const consoleErrs = (ctx.console_errors as ConsoleErrorEntry[] | undefined) ?? [];
  const networkErrs = (ctx.network_errors as NetworkErrorEntry[] | undefined) ?? [];

  return (
    <Drawer
      open={!!item}
      onClose={onClose}
      width={720}
      title={item.title}
      destroyOnHidden
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="Тип">
            <Tag color={item.kind === 'bug' ? 'red' : 'blue'}>
              {item.kind === 'bug' ? 'Баг' : 'Идея'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Автор">
            {item.author.display_name} ({item.author.email})
          </Descriptions.Item>
          <Descriptions.Item label="Создан">
            {new Date(item.created_at).toLocaleString('ru-RU')}
          </Descriptions.Item>
          {item.page_url && (
            <Descriptions.Item label="URL">{item.page_url}</Descriptions.Item>
          )}
        </Descriptions>

        <div>
          <Typography.Title level={5}>Описание</Typography.Title>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
            {item.body}
          </Typography.Paragraph>
        </div>

        {item.kind === 'bug' && (
          <>
            {item.steps_to_reproduce && (
              <div>
                <Typography.Title level={5}>Шаги воспроизведения</Typography.Title>
                <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
                  {item.steps_to_reproduce}
                </Typography.Paragraph>
              </div>
            )}
            {item.expected && (
              <div>
                <Typography.Title level={5}>Ожидание</Typography.Title>
                <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
                  {item.expected}
                </Typography.Paragraph>
              </div>
            )}
            {item.actual && (
              <div>
                <Typography.Title level={5}>Факт</Typography.Title>
                <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
                  {item.actual}
                </Typography.Paragraph>
              </div>
            )}
            <div>
              <Typography.Title level={5}>Контекст</Typography.Title>
              <Descriptions column={1} size="small" bordered>
                {ctx.user_agent !== undefined && (
                  <Descriptions.Item label="Браузер">
                    {String(ctx.user_agent)}
                  </Descriptions.Item>
                )}
                {ctx.screen_w !== undefined && (
                  <Descriptions.Item label="Экран">
                    {String(ctx.screen_w)}×{String(ctx.screen_h)}
                  </Descriptions.Item>
                )}
                {ctx.active_team !== undefined && (
                  <Descriptions.Item label="Команда">
                    {String(ctx.active_team)}
                  </Descriptions.Item>
                )}
                {ctx.active_period !== undefined && (
                  <Descriptions.Item label="Период">
                    {String(ctx.active_period)}
                  </Descriptions.Item>
                )}
                {ctx.theme !== undefined && (
                  <Descriptions.Item label="Тема">
                    {String(ctx.theme)}
                  </Descriptions.Item>
                )}
              </Descriptions>
            </div>
            <div>
              <Typography.Title level={5}>
                Консольные ошибки ({consoleErrs.length})
              </Typography.Title>
              {consoleErrs.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Нет" />
              ) : (
                <ol>
                  {consoleErrs.map((e, i) => (
                    <li key={i}>
                      <code>{String(e.message)}</code>
                    </li>
                  ))}
                </ol>
              )}
            </div>
            <div>
              <Typography.Title level={5}>
                Сетевые ошибки ({networkErrs.length})
              </Typography.Title>
              {networkErrs.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Нет" />
              ) : (
                <ol>
                  {networkErrs.map((e, i) => (
                    <li key={i}>
                      <code>
                        {String(e.method)} {String(e.url)} {String(e.status)}
                      </code>
                    </li>
                  ))}
                </ol>
              )}
            </div>
            {item.attachments.length > 0 && (
              <div>
                <Typography.Title level={5}>
                  Приложения ({item.attachments.length})
                </Typography.Title>
                <ul>
                  {item.attachments.map((a) => (
                    <li key={a.path}>
                      <Button
                        type="link"
                        href={`${BASE_URL}/feedback/attachments/${a.path}`}
                        target="_blank"
                      >
                        {a.filename} ({Math.round(a.size / 1024)} КБ)
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </Space>
    </Drawer>
  );
}
