import { useState } from 'react';
import { Card, Input, Button, Space, App } from 'antd';
import { Typography } from 'antd';
import { ApiOutlined, SaveOutlined } from '@ant-design/icons';
import { testConnection } from '../api/sync';
import { useJiraSettings, useSaveJiraSettings, useTestJiraCredentials } from '../hooks/useSettings';

const { Text } = Typography;

export default function ConnectionCard() {
  const { message } = App.useApp();
  const settings = useJiraSettings();
  const saveMutation = useSaveJiraSettings();
  const testMutation = useTestJiraCredentials();

  const [token, setToken] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [loaded, setLoaded] = useState(false);

  // Populate form from saved settings once
  if (settings.data && !loaded) {
    if (settings.data.base_url) setBaseUrl(settings.data.base_url);
    setLoaded(true);
  }

  const handleSave = () => {
    const body: { api_token?: string; base_url?: string } = {};
    if (token) body.api_token = token;
    if (baseUrl) body.base_url = baseUrl;
    saveMutation.mutate(body, {
      onSuccess: () => message.success('Настройки сохранены'),
      onError: (e) => message.error(e.message),
    });
  };

  const handleTest = () => {
    const testUrl = baseUrl || settings.data?.base_url || '';
    if (!testUrl) {
      message.warning('Укажите адрес Jira');
      return;
    }
    if (!token && !settings.data?.has_token) {
      message.warning('Укажите персональный токен');
      return;
    }
    // Новый токен не введён — проверяем сохранённые в базе адрес и токен
    if (!token && settings.data?.has_token) {
      testConnection().then((res) => {
        if (res.connected) message.success(`Подключение успешно (${res.user_name})`);
        else message.error(res.error || 'Не удалось подключиться');
      }).catch((e: Error) => message.error(e.message));
      return;
    }
    testMutation.mutate(
      { api_token: token, base_url: testUrl },
      {
        onSuccess: (res) => {
          if (res.connected) message.success(`Подключение успешно (${res.user_name})`);
          else message.error(res.error || 'Не удалось подключиться');
        },
        onError: (e) => message.error(e.message),
      },
    );
  };

  return (
    <Card title="Подключение к Jira" size="small">
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Space wrap>
          <Input
            placeholder="Адрес Jira (https://jira.example.ru)"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ width: 360 }}
            autoComplete="off"
            name="jira-base-url"
          />
          <Input.Password
            placeholder={settings.data?.has_token ? 'Токен сохранён (введите новый для замены)' : 'Персональный токен'}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ width: 300 }}
            autoComplete="new-password"
            name="jira-api-token"
          />
        </Space>
        <Space>
          <Button
            icon={<SaveOutlined />}
            type="primary"
            onClick={handleSave}
            loading={saveMutation.isPending}
          >
            Сохранить
          </Button>
          <Button
            icon={<ApiOutlined />}
            onClick={handleTest}
            loading={testMutation.isPending}
          >
            Проверить подключение
          </Button>
          {testMutation.data?.connected && (
            <Text type="success">{testMutation.data.user_name}</Text>
          )}
        </Space>
      </Space>
    </Card>
  );
}
