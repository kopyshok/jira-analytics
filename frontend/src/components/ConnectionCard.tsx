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

  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [loaded, setLoaded] = useState(false);

  // Populate form from saved settings once
  if (settings.data && !loaded) {
    if (settings.data.email) setEmail(settings.data.email);
    if (settings.data.base_url) setBaseUrl(settings.data.base_url);
    setLoaded(true);
  }

  const handleSave = () => {
    const body: Record<string, string> = {};
    if (email) body.email = email;
    if (token) body.api_token = token;
    if (baseUrl) body.base_url = baseUrl;
    saveMutation.mutate(body, {
      onSuccess: () => message.success('Настройки сохранены'),
      onError: (e) => message.error(e.message),
    });
  };

  const handleTest = () => {
    const testEmail = email || settings.data?.email || '';
    const testUrl = baseUrl || settings.data?.base_url || '';
    if (!testEmail || !testUrl) {
      message.warning('Укажите Email и Base URL');
      return;
    }
    if (!token && !settings.data?.has_token) {
      message.warning('Укажите API Token');
      return;
    }
    // If no new token, test via old endpoint (credentials are already in DB)
    if (!token && settings.data?.has_token) {
      testConnection().then((res) => {
        if (res.connected) message.success(`Подключение успешно (${res.user_name})`);
        else message.error(res.error || 'Не удалось подключиться');
      }).catch((e: Error) => message.error(e.message));
      return;
    }
    testMutation.mutate(
      { email: testEmail, api_token: token, base_url: testUrl },
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
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space wrap>
          <Input
            placeholder="Base URL (https://your-domain.atlassian.net)"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ width: 360 }}
          />
          <Input
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: 260 }}
          />
          <Input.Password
            placeholder={settings.data?.has_token ? 'Токен сохранён (введите новый для замены)' : 'API Token'}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ width: 300 }}
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
            <Text type="success">
              {testMutation.data.user_name} ({testMutation.data.user_email})
            </Text>
          )}
        </Space>
      </Space>
    </Card>
  );
}
