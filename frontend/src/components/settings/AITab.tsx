import React, { useEffect, useState } from 'react';
import { Button, Card, Form, Input, Select, Space, App, Typography, Tag, Divider, Alert, Switch } from 'antd';
import { EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import type { InputProps } from 'antd';
import {
  llmApi,
  type GeminiModelInfo,
  type OpenRouterModelInfo,
  type DeepSeekModelInfo,
  type PromptDefault,
} from '../../api/llm';
import { api } from '../../api/client';
import { aiStatusApi } from '../../api/aiStatus';
import { useAiEnabled } from '../../hooks/useAiEnabled';

const FALLBACK_GEMINI_MODELS: GeminiModelInfo[] = [
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

const FALLBACK_OPENROUTER_MODELS: OpenRouterModelInfo[] = [
  { id: 'qwen/qwen3-next-80b-a3b-instruct:free', label: 'Qwen3-Next 80B Instruct (free, рекомендуется)', context_length: 262144 },
  { id: 'nousresearch/hermes-3-llama-3.1-405b:free', label: 'Hermes 3 Llama 3.1 405B (free)', context_length: 131072 },
  { id: 'google/gemma-3-27b-it:free', label: 'Gemma 3 27B IT (free)', context_length: 131072 },
  { id: 'z-ai/glm-4.5-air:free', label: 'GLM 4.5 Air (free)', context_length: 131072 },
  { id: 'openai/gpt-oss-120b:free', label: 'GPT-OSS 120B (free)', context_length: 131072 },
  { id: 'qwen/qwen3-coder:free', label: 'Qwen3 Coder (free)', context_length: 262000 },
];

const RECOMMENDED_GEMINI = 'gemini-3.1-flash-lite-preview';
const RECOMMENDED_OPENROUTER = 'qwen/qwen3-next-80b-a3b-instruct:free';
const RECOMMENDED_DEEPSEEK = 'deepseek-chat';
const FALLBACK_DEEPSEEK_MODELS: DeepSeekModelInfo[] = [
  { id: 'deepseek-chat', label: 'DeepSeek V3.2 (chat, дешёвый, рекомендуется)' },
  { id: 'deepseek-reasoner', label: 'DeepSeek R1 (reasoner, SOTA reasoning, дороже)' },
];
const PROMPT_KEY = 'llm_project_summary_system_prompt';

type FormValues = {
  provider: string;
  gemini_key: string;
  gemini_model: string;
  openrouter_key: string;
  openrouter_model: string;
  openrouter_fallback_models: string[];
  deepseek_key: string;
  deepseek_model: string;
  prompt_role: string;
};

const DEFAULT_OPENROUTER_FALLBACKS = [
  'nousresearch/hermes-3-llama-3.1-405b:free',
  'openai/gpt-oss-120b:free',
  'google/gemma-3-27b-it:free',
];

export const AITab: React.FC = () => {
  const { message, modal } = App.useApp();
  const queryClient = useQueryClient();
  const { enabled: aiEnabled, isLoading: aiStatusLoading } = useAiEnabled();
  const [form] = Form.useForm<FormValues>();
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState<string>('gemini');
  const [switching, setSwitching] = useState(false);

  const onToggleAi = async (next: boolean) => {
    setSwitching(true);
    try {
      await aiStatusApi.set(next);
      await queryClient.invalidateQueries({ queryKey: ['ai-status'] });
      message.success(next ? 'ИИ включён' : 'ИИ выключен');
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : 'Не удалось сменить состояние');
    } finally {
      setSwitching(false);
    }
  };

  const [geminiModels, setGeminiModels] = useState<GeminiModelInfo[]>(FALLBACK_GEMINI_MODELS);
  const [geminiModelsLoading, setGeminiModelsLoading] = useState(false);

  const [openRouterModels, setOpenRouterModels] = useState<OpenRouterModelInfo[]>(FALLBACK_OPENROUTER_MODELS);
  const [openRouterModelsLoading, setOpenRouterModelsLoading] = useState(false);

  const [deepSeekModels, setDeepSeekModels] = useState<DeepSeekModelInfo[]>(FALLBACK_DEEPSEEK_MODELS);
  const [deepSeekModelsLoading, setDeepSeekModelsLoading] = useState(false);

  const [promptDefault, setPromptDefault] = useState<PromptDefault | null>(null);

  useEffect(() => {
    (async () => {
      const prov = await loadSetting('llm_provider', 'gemini');
      const geminiKey = await loadSetting('llm_gemini_api_key', '');
      const geminiModel = await loadSetting('llm_gemini_model', RECOMMENDED_GEMINI);
      const openRouterKey = await loadSetting('llm_openrouter_api_key', '');
      const openRouterModel = await loadSetting('llm_openrouter_model', RECOMMENDED_OPENROUTER);
      const fallbackCsv = await loadSetting(
        'llm_openrouter_fallback_models',
        DEFAULT_OPENROUTER_FALLBACKS.join(','),
      );
      const fallbackList = fallbackCsv.split(',').map((s) => s.trim()).filter(Boolean);
      const deepSeekKey = await loadSetting('llm_deepseek_api_key', '');
      const deepSeekModel = await loadSetting('llm_deepseek_model', RECOMMENDED_DEEPSEEK);
      const def = await llmApi.getPromptDefault().catch(() => null);
      setPromptDefault(def);
      const promptRole = (await loadSetting(PROMPT_KEY, '')) || (def?.system_role ?? '');
      setProvider(prov);
      form.setFieldsValue({
        provider: prov,
        gemini_key: geminiKey,
        gemini_model: geminiModel,
        openrouter_key: openRouterKey,
        openrouter_model: openRouterModel,
        openrouter_fallback_models: fallbackList,
        deepseek_key: deepSeekKey,
        deepseek_model: deepSeekModel,
        prompt_role: promptRole,
      });
      const status = await aiStatusApi.get().catch(() => ({ enabled: false }));
      if (status.enabled && geminiKey) await refreshGeminiModels(true);
      if (status.enabled && openRouterKey) await refreshOpenRouterModels(true);
      if (status.enabled && deepSeekKey) await refreshDeepSeekModels(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshGeminiModels = async (silent = false) => {
    setGeminiModelsLoading(true);
    try {
      const list = await llmApi.listGeminiModels();
      if (list && list.length) setGeminiModels(list);
      if (!silent) message.success(`Загружено ${list.length} моделей Gemini`);
    } catch (e: unknown) {
      if (!silent) message.error(e instanceof Error ? e.message : 'Не удалось загрузить список');
    } finally {
      setGeminiModelsLoading(false);
    }
  };

  const refreshOpenRouterModels = async (silent = false) => {
    setOpenRouterModelsLoading(true);
    try {
      const list = await llmApi.listOpenRouterModels();
      if (list && list.length) setOpenRouterModels(list);
      if (!silent) message.success(`Загружено ${list.length} бесплатных моделей OpenRouter`);
    } catch (e: unknown) {
      if (!silent) message.error(e instanceof Error ? e.message : 'Не удалось загрузить список');
    } finally {
      setOpenRouterModelsLoading(false);
    }
  };

  const refreshDeepSeekModels = async (silent = false) => {
    setDeepSeekModelsLoading(true);
    try {
      const list = await llmApi.listDeepSeekModels();
      if (list && list.length) setDeepSeekModels(list);
      if (!silent) message.success(`Загружено ${list.length} моделей DeepSeek`);
    } catch (e: unknown) {
      if (!silent) message.error(e instanceof Error ? e.message : 'Не удалось загрузить список');
    } finally {
      setDeepSeekModelsLoading(false);
    }
  };

  const onSave = async (values: FormValues) => {
    setLoading(true);
    try {
      await api.put('/settings/generic', { key: 'llm_provider', value: values.provider });

      await api.put('/settings/generic', { key: 'llm_gemini_model', value: values.gemini_model });
      if (values.gemini_key) {
        await api.put('/settings/generic', { key: 'llm_gemini_api_key', value: values.gemini_key });
      }

      await api.put('/settings/generic', { key: 'llm_openrouter_model', value: values.openrouter_model });
      await api.put('/settings/generic', {
        key: 'llm_openrouter_fallback_models',
        value: (values.openrouter_fallback_models || []).join(','),
      });
      if (values.openrouter_key) {
        await api.put('/settings/generic', { key: 'llm_openrouter_api_key', value: values.openrouter_key });
      }

      await api.put('/settings/generic', { key: 'llm_deepseek_model', value: values.deepseek_model });
      if (values.deepseek_key) {
        await api.put('/settings/generic', { key: 'llm_deepseek_api_key', value: values.deepseek_key });
      }

      const role = (values.prompt_role ?? '').trim();
      const isDefault = promptDefault && role === promptDefault.system_role.trim();
      await api.put('/settings/generic', {
        key: PROMPT_KEY,
        value: isDefault || !role ? null : values.prompt_role,
      });
      message.success('Настройки AI сохранены');
    } finally {
      setLoading(false);
    }
  };

  const onTest = async () => {
    try {
      const r = await llmApi.test();
      if (r.ok) {
        message.success(`${r.provider} ${r.model}: подключение работает`);
      } else {
        modal.error({
          title: `${r.provider} ${r.model}: подключение не удалось`,
          content: r.error || 'Причина неизвестна (см. логи backend).',
          width: 720,
        });
      }
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

  const onResetPrompt = () => {
    if (!promptDefault) return;
    modal.confirm({
      title: 'Сбросить промпт к дефолту?',
      content: 'Текущий текст будет заменён стандартным.',
      okText: 'Сбросить',
      cancelText: 'Отмена',
      onOk: () => {
        form.setFieldValue('prompt_role', promptDefault.system_role);
      },
    });
  };

  const geminiOptions = geminiModels.map((m) => ({
    value: m.id,
    label: (
      <span>
        {m.label}
        {m.id === RECOMMENDED_GEMINI && (
          <Tag color="green" style={{ marginLeft: 8 }}>
            free 15 RPM / 500 RPD
          </Tag>
        )}
      </span>
    ),
    searchText: `${m.label} ${m.id}`,
  }));

  const openRouterOptions = openRouterModels.map((m) => ({
    value: m.id,
    label: (
      <span>
        {m.label}{' '}
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          {m.id} · {Math.round(m.context_length / 1000)}k ctx
        </Typography.Text>
        {m.id === RECOMMENDED_OPENROUTER && (
          <Tag color="green" style={{ marginLeft: 8 }}>
            рекомендуется
          </Tag>
        )}
      </span>
    ),
    searchText: `${m.label} ${m.id}`,
  }));

  return (
    <Card
      title="AI-провайдер"
      extra={
        <Space>
          <Typography.Text>ИИ включён</Typography.Text>
          <Switch
            checked={aiEnabled}
            loading={switching || aiStatusLoading}
            onChange={onToggleAi}
          />
          <Button onClick={onRegenAll} disabled={!aiEnabled}>
            Перегенерировать все саммари
          </Button>
        </Space>
      }
    >
      {!aiEnabled && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title="ИИ выключен администратором"
          description="Все AI-вызовы заблокированы (саммари проектов, тематический отчёт, executive AI-сводка). Существующие сгенерированные данные остаются видимыми. Чтобы включить — переведите переключатель «ИИ включён» в правом верхнем углу."
        />
      )}
      <Form
        form={form}
        layout="vertical"
        onFinish={onSave}
        disabled={loading || !aiEnabled}
        autoComplete="off"
        onValuesChange={(changed) => {
          if (changed.provider) setProvider(changed.provider);
        }}
      >
        <Form.Item label="Провайдер" name="provider">
          <Select
            options={[
              { value: 'gemini', label: 'Google Gemini' },
              { value: 'openrouter', label: 'OpenRouter (десятки free-моделей)' },
              { value: 'deepseek', label: 'DeepSeek (прямой API, платный)' },
              { value: 'anthropic', label: 'Anthropic Claude (заглушка)', disabled: true },
              { value: 'openai', label: 'OpenAI GPT (заглушка)', disabled: true },
            ]}
          />
        </Form.Item>

        <div style={{ display: provider === 'gemini' ? 'block' : 'none' }}>
          <Form.Item
            label={
              <Space>
                <span>Модель Gemini</span>
                <Button
                  size="small"
                  type="link"
                  loading={geminiModelsLoading}
                  onClick={() => refreshGeminiModels(false)}
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
            <Select options={geminiOptions} optionLabelProp="label" popupMatchSelectWidth={false} />
          </Form.Item>

          <Form.Item
            label="API key (Gemini)"
            name="gemini_key"
            extra="Получить ключ можно на makersuite.google.com"
          >
            <MaskedInput placeholder="AIza..." name="gemini_api_key_field" />
          </Form.Item>
        </div>

        <div style={{ display: provider === 'openrouter' ? 'block' : 'none' }}>
          <Form.Item
            label={
              <Space>
                <span>Модель OpenRouter</span>
                <Button
                  size="small"
                  type="link"
                  loading={openRouterModelsLoading}
                  onClick={() => refreshOpenRouterModels(false)}
                >
                  Обновить список
                </Button>
              </Space>
            }
            name="openrouter_model"
            extra={
              <Typography.Text type="secondary">
                Только бесплатные модели (суффикс «:free»). Общая квота на ключ — ~20 RPM / 50 RPD
                на все free-модели вместе. DeepSeek V3.1 — лучший русский + большой контекст.
                При 429 — подождать минуту или сменить модель.
              </Typography.Text>
            }
          >
            <Select options={openRouterOptions} optionLabelProp="label" popupMatchSelectWidth={false} />
          </Form.Item>

          <Form.Item
            label="Запасные модели (fallback)"
            name="openrouter_fallback_models"
            extra={
              <Typography.Text type="secondary">
                При 429/5xx или некорректном ответе основной модели — пробуем по порядку
                эту цепочку. Используйте модели РАЗНЫХ провайдеров для устойчивости.
                Дефолт: Hermes 405B → GPT-OSS 120B → Gemma 3 27B.
              </Typography.Text>
            }
          >
            <Select
              mode="multiple"
              options={openRouterOptions}
              optionLabelProp="label"
              popupMatchSelectWidth={false}
              placeholder="Выберите модели для авто-перебора при ошибке"
            />
          </Form.Item>

          <Form.Item
            label="API key (OpenRouter)"
            name="openrouter_key"
            extra="Получить ключ: openrouter.ai/keys"
          >
            <MaskedInput placeholder="sk-or-v1-..." name="openrouter_api_key_field" />
          </Form.Item>
        </div>

        <div style={{ display: provider === 'deepseek' ? 'block' : 'none' }}>
          <Form.Item
            label={
              <Space>
                <span>Модель DeepSeek</span>
                <Button
                  size="small"
                  type="link"
                  loading={deepSeekModelsLoading}
                  onClick={() => refreshDeepSeekModels(false)}
                >
                  Обновить список
                </Button>
              </Space>
            }
            name="deepseek_model"
            extra={
              <Typography.Text type="secondary">
                deepseek-chat = V3.2 ($0.27/M in, $1.10/M out) — рекомендуется.
                deepseek-reasoner = R1 chain-of-thought (~$0.55/M in, $2.19/M out).
                Контекст 64K, max output 8K. Free tier нет.
              </Typography.Text>
            }
          >
            <Select
              options={deepSeekModels.map((m) => ({
                value: m.id,
                label: (
                  <span>
                    {m.label}
                    {m.id === RECOMMENDED_DEEPSEEK && (
                      <Tag color="green" style={{ marginLeft: 8 }}>
                        рекомендуется
                      </Tag>
                    )}
                  </span>
                ),
                searchText: `${m.label} ${m.id}`,
              }))}
              optionLabelProp="label"
              popupMatchSelectWidth={false}
            />
          </Form.Item>

          <Form.Item
            label="API key (DeepSeek)"
            name="deepseek_key"
            extra="Получить ключ: platform.deepseek.com/api_keys"
          >
            <MaskedInput placeholder="sk-..." name="deepseek_api_key_field" />
          </Form.Item>
        </div>

        <Divider plain>Системный промпт саммари</Divider>

        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          title="Редактируется только роль / тон / стиль"
          description="Описание JSON-формата (поля goals, result_checklist, work_breakdown и т.д.) — фиксированное и подмешивается автоматически. Менять формат через UI нельзя — иначе сломается парсинг ответа."
        />

        <Form.Item
          label={
            <Space>
              <span>Текст промпта (роль и инструкции стиля)</span>
              <Button size="small" type="link" onClick={onResetPrompt} disabled={!promptDefault}>
                Сбросить к дефолту
              </Button>
            </Space>
          }
          name="prompt_role"
          extra={
            <Typography.Text type="secondary">
              При смене текста все существующие саммари помечаются устаревшими и
              будут перегенерированы в ближайший проход (или сразу — кнопка
              «Перегенерировать все саммари»).
            </Typography.Text>
          }
        >
          <Input.TextArea autoSize={{ minRows: 6, maxRows: 20 }} />
        </Form.Item>

        {promptDefault && (
          <Form.Item label="Описание формата (read-only)">
            <Input.TextArea
              value={promptDefault.format_spec}
              readOnly
              autoSize={{ minRows: 4, maxRows: 12 }}
              style={{ background: 'rgba(255,255,255,0.04)', cursor: 'not-allowed' }}
            />
          </Form.Item>
        )}

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

/**
 * Текстовый Input с CSS-маскировкой (`-webkit-text-security: disc`) и
 * глазиком-переключателем. Не использует `type="password"` — браузер не
 * предлагает сохранить пароль.
 */
const MaskedInput: React.FC<InputProps> = (props) => {
  const [visible, setVisible] = useState(false);
  return (
    <Input
      {...props}
      autoComplete="off"
      style={{
        ...(props.style || {}),
        WebkitTextSecurity: visible ? 'none' : 'disc',
        textSecurity: visible ? 'none' : 'disc',
      } as React.CSSProperties}
      suffix={
        <Button
          type="text"
          size="small"
          icon={visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
          onClick={() => setVisible((v) => !v)}
          tabIndex={-1}
          style={{ border: 'none', padding: 0 }}
        />
      }
    />
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
