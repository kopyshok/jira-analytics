import React, { useEffect, useState } from 'react';
import { Button, Card, Form, Input, Select, Space, App, Typography, Tag } from 'antd';
import { llmApi, type GeminiModelInfo } from '../../api/llm';
import { api } from '../../api/client';

const FALLBACK_MODELS: GeminiModelInfo[] = [
  { id: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite Preview (рекомендуется на free)', version: 3.1 },
  { id: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro Preview', version: 3.1 },
  { id: 'gemini-3-flash-preview', label: 'Gemini 3 Flash Preview', version: 3.0 },
  { id: 'gemini-3-pro-preview', label: 'Gemini 3 Pro Preview', version: 3.0 },
  { id: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite', version: 2.5 },
  { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', version: 2.5 },
  { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', version: 2.5 },
  { id: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite', version: 2.0 },
  { id: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash', version: 2.0 },
];

const RECOMMENDED_FREE = 'gemini-3.1-flash-lite-preview';

export const AITab: React.FC = () => {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<GeminiModelInfo[]>(FALLBACK_MODELS);
  const [modelsLoading, setModelsLoading] = useState(false);

  useEffect(() => {
    (async () => {
      const provider = await loadSetting('llm_provider', 'gemini');
      const geminiKey = await loadSetting('llm_gemini_api_key', '');
      const geminiModel = await loadSetting('llm_gemini_model', RECOMMENDED_FREE);
      form.setFieldsValue({ provider, gemini_key: geminiKey, gemini_model: geminiModel });
      if (geminiKey) await refreshModels(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshModels = async (silent = false) => {
    setModelsLoading(true);
    try {
      const list = await llmApi.listGeminiModels();
      if (list && list.length) setModels(list);
      if (!silent) message.success(`Загружено ${list.length} моделей`);
    } catch (e: unknown) {
      if (!silent) message.error(e instanceof Error ? e.message : 'Не удалось загрузить список');
    } finally {
      setModelsLoading(false);
    }
  };

  const onSave = async (values: { provider: string; gemini_key: string; gemini_model: string }) => {
    setLoading(true);
    try {
      await api.put('/settings/generic', { key: 'llm_provider', value: values.provider });
      await api.put('/settings/generic', { key: 'llm_gemini_model', value: values.gemini_model });
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

  const modelOptions = models.map((m) => ({
    value: m.id,
    label: (
      <span>
        {m.label}
        {m.id === RECOMMENDED_FREE && (
          <Tag color="green" style={{ marginLeft: 8 }}>
            free 15 RPM / 500 RPD
          </Tag>
        )}
      </span>
    ),
    searchText: `${m.label} ${m.id}`,
  }));

  return (
    <Card
      title="AI-провайдер"
      extra={<Button onClick={onRegenAll}>Перегенерировать все саммари</Button>}
    >
      <Form form={form} layout="vertical" onFinish={onSave} disabled={loading} autoComplete="off">
        <Form.Item label="Провайдер" name="provider">
          <Select
            options={[
              { value: 'gemini', label: 'Google Gemini' },
              { value: 'deepseek', label: 'DeepSeek V3 (заглушка)', disabled: true },
              { value: 'anthropic', label: 'Anthropic Claude (заглушка)', disabled: true },
              { value: 'openai', label: 'OpenAI GPT (заглушка)', disabled: true },
            ]}
          />
        </Form.Item>

        <Form.Item
          label={
            <Space>
              <span>Модель Gemini</span>
              <Button
                size="small"
                type="link"
                loading={modelsLoading}
                onClick={() => refreshModels(false)}
              >
                Обновить список
              </Button>
            </Space>
          }
          name="gemini_model"
          extra={
            <Typography.Text type="secondary">
              Free tier лимиты разные. 3.1 Flash Lite = 15 RPM × 500 RPD (лучше всех).
              2.5 Flash = 5 RPM × 20 RPD (быстро упрётся). Pro / 2.0 — только paid.
              При HTTP 429 «too many requests» — переключитесь на модель с большей квотой.
            </Typography.Text>
          }
        >
          <Select
            options={modelOptions}
            optionLabelProp="label"
            popupMatchSelectWidth={false}
          />
        </Form.Item>

        <Form.Item
          label="API key (Gemini)"
          name="gemini_key"
          extra="Получить ключ можно на makersuite.google.com"
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
