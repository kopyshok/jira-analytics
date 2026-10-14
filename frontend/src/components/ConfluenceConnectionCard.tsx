import { useState } from 'react';
import { Card, Input, Button, Space, App, Typography } from 'antd';
import { ApiOutlined, SaveOutlined } from '@ant-design/icons';
import {
  useConfluenceSettings, useSaveConfluenceSettings, useTestConfluenceConnection,
} from '../hooks/useSettings';

const { Text } = Typography;

/** Подключение к Confluence: свой адрес и персональный токен (сервер отдельный от Jira). */
export default function ConfluenceConnectionCard() {
  const { message } = App.useApp();
  const settings = useConfluenceSettings();
  const saveMutation = useSaveConfluenceSettings();
  const testMutation = useTestConfluenceConnection();

  const [token, setToken] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [loaded, setLoaded] = useState(false);

  if (settings.data && !loaded) {
    if (settings.data.base_url) setBaseUrl(settings.data.base_url);
    setLoaded(true);
  }

  const handleSave = () => {
    const body: { api_token?: string; base_url?: string } = {};
    if (token) body.api_token = token;
    if (baseUrl) body.base_url = baseUrl;
    if (!body.api_token && !body.base_url) {
      message.info('Нечего сохранять');
      return;
    }
    saveMutation.mutate(body, {
      onSuccess: () => {
        setToken('');
        testMutation.reset();
        message.success('Настройки сохранены');
      },
      onError: (e) => message.error(e.message),
    });
  };

  const handleTest = () => {
    if (!settings.data?.base_url || !settings.data?.has_token) {
      message.warning('Сначала сохраните адрес и токен Confluence');
      return;
    }
    testMutation.mutate(undefined, {
      onSuccess: (res) => {
        if (res.connected) message.success(res.user_name ? `Подключение успешно (${res.user_name})` : 'Подключение успешно');
        else message.error(res.error || 'Не удалось подключиться');
      },
      onError: (e) => message.error(e.message),
    });
  };

  return (
    <Card title="Подключение к Confluence" size="small">
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Text type="secondary">
          Страницы Confluence из описаний задач подтягиваются в сводку проекта.
        </Text>
        <Space wrap>
          <Input
            placeholder="Адрес Confluence (https://confluence.example.ru)"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ width: 360 }}
            autoComplete="off"
            name="confluence-base-url"
          />
          <Input.Password
            placeholder={settings.data?.has_token ? 'Токен сохранён (введите новый для замены)' : 'Персональный токен'}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ width: 300 }}
            autoComplete="new-password"
            name="confluence-api-token"
          />
        </Space>
        <Space>
          <Button icon={<SaveOutlined />} type="primary" onClick={handleSave} loading={saveMutation.isPending}>
            Сохранить
          </Button>
          <Button icon={<ApiOutlined />} onClick={handleTest} loading={testMutation.isPending}>
            Проверить подключение
          </Button>
          {testMutation.data?.connected && <Text type="success">{testMutation.data.user_name}</Text>}
        </Space>
      </Space>
    </Card>
  );
}
