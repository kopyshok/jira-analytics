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

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmitted?: () => void;
}

interface BugFormValues {
  title: string;
  body: string;
  steps_to_reproduce?: string;
  expected?: string;
  actual?: string;
}

interface IdeaFormValues {
  title: string;
  body: string;
}

const MAX_FILES = 5;
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB

export default function FeedbackDrawer({ open, onClose, onSubmitted }: Props) {
  const { notification } = App.useApp();
  const [kind, setKind] = useState<FeedbackKind>('bug');
  const [bugForm] = Form.useForm<BugFormValues>();
  const [ideaForm] = Form.useForm<IdeaFormValues>();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const close = () => {
    bugForm.resetFields();
    ideaForm.resetFields();
    setFileList([]);
    setKind('bug');
    onClose();
  };

  const handleSubmitBug = async () => {
    let values: BugFormValues;
    try {
      values = await bugForm.validateFields();
    } catch {
      return;
    }
    setSubmitting(true);
    try {
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

  const handleSubmitIdea = async () => {
    let values: IdeaFormValues;
    try {
      values = await ideaForm.validateFields();
    } catch {
      return;
    }
    setSubmitting(true);
    try {
      await feedbackApi.createIdea({
        title: values.title,
        body: values.body,
        page_url: window.location.href,
      });
      notification.success({ title: 'Идея отправлена', description: 'Спасибо! Идея появится в общей ленте.' });
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

  const handleSubmit = () => {
    if (kind === 'bug') void handleSubmitBug();
    else void handleSubmitIdea();
  };

  return (
    <Drawer
      title="Обратная связь"
      open={open}
      onClose={close}
      width={560}
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
        onChange={(e) => setKind(e.target.value as FeedbackKind)}
        optionType="button"
        buttonStyle="solid"
        style={{ marginBottom: 16 }}
        options={[
          { label: 'Баг', value: 'bug' },
          { label: 'Идея', value: 'idea' },
        ]}
      />

      {kind === 'bug' ? (
        <Form form={bugForm} layout="vertical" preserve={false}>
          <Form.Item
            name="title"
            label="Заголовок"
            rules={[{ required: true, message: 'Опишите проблему в одну строку' }]}
          >
            <Input placeholder="Что не работает (одной строкой)" maxLength={255} />
          </Form.Item>
          <Form.Item
            name="body"
            label="Что случилось"
            rules={[{ required: true, message: 'Опишите подробнее' }]}
          >
            <Input.TextArea rows={4} placeholder="Подробное описание проблемы" />
          </Form.Item>
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
            message="Автоматически прикрепится"
            description="URL страницы, браузер и ОС, активная команда и период, тема, последние ошибки из консоли и сети."
            style={{ marginTop: 8 }}
          />
        </Form>
      ) : (
        <Form form={ideaForm} layout="vertical" preserve={false}>
          <Form.Item
            name="title"
            label="Заголовок"
            rules={[{ required: true, message: 'Сформулируйте идею одной строкой' }]}
          >
            <Input placeholder="Суть идеи одной строкой" maxLength={255} />
          </Form.Item>
          <Form.Item
            name="body"
            label="Описание"
            rules={[{ required: true, message: 'Поясните идею' }]}
          >
            <Input.TextArea
              rows={6}
              placeholder="Что улучшить, зачем, кому это будет полезно"
            />
          </Form.Item>
        </Form>
      )}
    </Drawer>
  );
}
