import React, { useEffect, useState } from 'react';
import { Button, Card, Form, Input, Select, Space, App } from 'antd';
import { llmApi } from '../../api/llm';
import { api } from '../../api/client';

export const AITab: React.FC = () => {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      const provider = await loadSetting('llm_provider', 'gemini');
      const geminiKey = await loadSetting('llm_gemini_api_key', '');
      form.setFieldsValue({ provider, gemini_key: geminiKey });
    })();
  }, [form]);

  const onSave = async (values: { provider: string; gemini_key: string }) => {
    setLoading(true);
    try {
      await api.put('/settings/generic', { key: 'llm_provider', value: values.provider });
      if (values.gemini_key) {
        await api.put('/settings/generic', { key: 'llm_gemini_api_key', value: values.gemini_key });
      }
      message.success('Настройки AI сохранены');
    } finally {
      setLoading(false);
    }
  };

  const onTest = async () => {
    try {
      const r = await llmApi.test();
      if (r.ok) message.success(`${r.provider} ${r.model}: подключение работает`);
      else message.warning(`${r.provider} ${r.model}: подключение не удалось`);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : 'Ошибка подключения');
    }
  };

  const onRegenAll = async () => {
    try {
      await llmApi.regenerateAll();
      message.info('Регенерация запущена в фоне');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : 'Не удалось запустить');
    }
  };

  return (
    <Card
      title="AI-провайдер"
      extra={<Button onClick={onRegenAll}>Перегенерировать все саммари</Button>}
    >
      <Form form={form} layout="vertical" onFinish={onSave} disabled={loading}>
        <Form.Item label="Провайдер" name="provider">
          <Select
            options={[
              { value: 'gemini', label: 'Google Gemini 2.0 Flash (рекомендуется)' },
              { value: 'deepseek', label: 'DeepSeek V3 (заглушка)', disabled: true },
              { value: 'anthropic', label: 'Anthropic Claude (заглушка)', disabled: true },
              { value: 'openai', label: 'OpenAI GPT (заглушка)', disabled: true },
            ]}
          />
        </Form.Item>

        <Form.Item
          label="API key (Gemini)"
          name="gemini_key"
          extra="Получить ключ можно на makersuite.google.com — бесплатный tier 15 RPM"
        >
          <Input.Password placeholder="AIza..." autoComplete="off" />
        </Form.Item>

        <Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={loading}>
              Сохранить
            </Button>
            <Button onClick={onTest}>Проверить подключение</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );
};

async function loadSetting(key: string, fallback: string): Promise<string> {
  try {
    const r = await api.get<{ key: string; value: string }>(
      `/settings/generic/${encodeURIComponent(key)}`,
    );
    return r.value ?? fallback;
  } catch {
    return fallback;
  }
}
