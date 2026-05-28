import { useState } from 'react';
import {
  Drawer,
  Form,
  Input,
  Radio,
  Upload,
  Button,
  App,
  Alert,
} from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { feedbackApi, type AttachmentRef, type FeedbackKind } from '../../api/feedback';
import { buildContext } from '../../utils/errorStore';
import { DARK_THEME } from '../../utils/constants';
import { trackAction } from '../../lib/usage/track';

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmitted?: () => void;
}

interface FeedbackFormValues {
  title: string;
  body: string;
  steps_to_reproduce?: string;
  expected?: string;
  actual?: string;
}

const MAX_FILES = 5;
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB

export default function FeedbackDrawer({ open, onClose, onSubmitted }: Props) {
  const { notification } = App.useApp();
  const [kind, setKind] = useState<FeedbackKind>('bug');
  const [form] = Form.useForm<FeedbackFormValues>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const close = () => {
    form.resetFields();
    setFileList([]);
    setKind('bug');
    onClose();
  };

  const handleKindChange = (next: FeedbackKind) => {
    form.resetFields();
    setKind(next);
  };

  const handleSubmit = async () => {
    let values: FeedbackFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSubmitting(true);
    try {
      if (kind === 'bug') {
        const attachments: AttachmentRef[] = [];
        for (const item of fileList) {
          if (!item.originFileObj) continue;
          const ref = await feedbackApi.uploadAttachment(item.originFileObj as File);
          attachments.push(ref);
        }
        const context = buildContext() as unknown as Record<string, unknown>;
        await feedbackApi.createBug({
          title: values.title,
          body: values.body,
          steps_to_reproduce: values.steps_to_reproduce,
          expected: values.expected,
          actual: values.actual,
          page_url: window.location.href,
          context,
          attachments: attachments.length > 0 ? attachments : undefined,
        });
        notification.success({ title: 'Баг отправлен', description: 'Спасибо! Мы разберём в ближайшее время.' });
      } else {
        await feedbackApi.createIdea({
          title: values.title,
          body: values.body,
          page_url: window.location.href,
        });
        notification.success({ title: 'Идея отправлена', description: 'Спасибо! Идея появится в общей ленте.' });
      }
      trackAction('feedback_submitted');
      close();
      onSubmitted?.();
    } catch (e) {
      notification.error({
        title: 'Не удалось отправить',
        description: (e as Error).message,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title="Обратная связь"
      open={open}
      onClose={close}
      styles={{ wrapper: { width: 560 } }}
      destroyOnHidden
      footer={
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button onClick={close} disabled={submitting}>Отмена</Button>
          <Button type="primary" onClick={handleSubmit} loading={submitting}>
            Отправить
          </Button>
        </div>
      }
    >
      <Radio.Group
        value={kind}
        onChange={(e) => handleKindChange(e.target.value as FeedbackKind)}
        optionType="button"
        buttonStyle="solid"
        style={{ marginBottom: 16 }}
        options={[
          { label: 'Баг', value: 'bug' },
          { label: 'Идея', value: 'idea' },
        ]}
      />

      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="title"
          label="Заголовок"
          rules={[
            {
              required: true,
              message: kind === 'bug'
                ? 'Опишите проблему в одну строку'
                : 'Сформулируйте идею одной строкой',
            },
          ]}
        >
          <Input
            placeholder={kind === 'bug' ? 'Что не работает (одной строкой)' : 'Суть идеи одной строкой'}
            maxLength={255}
          />
        </Form.Item>
        <Form.Item
          name="body"
          label={kind === 'bug' ? 'Что случилось' : 'Описание'}
          rules={[
            {
              required: true,
              message: kind === 'bug' ? 'Опишите подробнее' : 'Поясните идею',
            },
          ]}
        >
          <Input.TextArea
            rows={kind === 'bug' ? 4 : 6}
            placeholder={
              kind === 'bug'
                ? 'Подробное описание проблемы'
                : 'Что улучшить, зачем, кому это будет полезно'
            }
          />
        </Form.Item>

        {kind === 'bug' && (
          <>
            <Form.Item name="steps_to_reproduce" label="Шаги воспроизведения">
              <Input.TextArea rows={3} placeholder="По шагам, что вы делали" />
            </Form.Item>
            <Form.Item name="expected" label="Что ожидали">
              <Input.TextArea rows={2} placeholder="Что должно было произойти" />
            </Form.Item>
            <Form.Item name="actual" label="Что произошло на самом деле">
              <Input.TextArea rows={2} placeholder="Что произошло вместо этого" />
            </Form.Item>
            <Form.Item label="Приложения (до 5 файлов, 5 МБ каждый)">
              <Upload.Dragger
                multiple
                fileList={fileList}
                beforeUpload={(file) => {
                  if (file.size > MAX_FILE_SIZE) {
                    notification.error({
                      title: 'Файл слишком большой',
                      description: `${file.name}: больше 5 МБ`,
                    });
                    return Upload.LIST_IGNORE;
                  }
                  if (fileList.length >= MAX_FILES) {
                    notification.error({
                      title: 'Слишком много файлов',
                      description: 'Не больше 5 файлов за раз',
                    });
                    return Upload.LIST_IGNORE;
                  }
                  return false;
                }}
                onChange={(info) => setFileList(info.fileList.slice(0, MAX_FILES))}
                onRemove={(file) => {
                  setFileList((prev) => prev.filter((f) => f.uid !== file.uid));
                }}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text" style={{ fontSize: 13 }}>
                  Перетащите файлы сюда или нажмите для выбора
                </p>
                <p className="ant-upload-hint" style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                  Скриншоты, логи, текст — что угодно по теме
                </p>
              </Upload.Dragger>
            </Form.Item>
            <Alert
              type="info"
              showIcon
              title="Автоматически прикрепится"
              description="URL страницы, браузер и ОС, активная команда и период, тема, последние ошибки из консоли и сети."
              style={{ marginTop: 8 }}
            />
          </>
        )}
      </Form>
    </Drawer>
  );
}
