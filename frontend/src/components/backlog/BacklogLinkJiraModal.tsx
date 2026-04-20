import { useEffect } from 'react';
import { Alert, App, Form, Input, Modal } from 'antd';
import { useLinkJira } from '../../hooks/useBacklog';
import type { BacklogItemResponse } from '../../types/api';

interface Props {
  open: boolean;
  item: BacklogItemResponse | null;
  onClose: () => void;
}

interface FormValues {
  jira_key: string;
}

export default function BacklogLinkJiraModal({ open, item, onClose }: Props) {
  const { notification } = App.useApp();
  const link = useLinkJira();
  const [form] = Form.useForm<FormValues>();

  useEffect(() => {
    if (open) form.resetFields();
  }, [open, form]);

  const handleSubmit = (values: FormValues) => {
    if (!item) return;
    const key = values.jira_key.trim().toUpperCase();
    link.mutate(
      { id: item.id, jira_key: key },
      {
        onSuccess: () => {
          notification.success({ title: 'Связано с Jira', description: key });
          onClose();
        },
        onError: (e) => {
          const msg = (e as Error).message || 'Не удалось связать';
          // Backend surfaces 404 ("not found locally") and 409 ("already linked")
          // as Error(detail) — show detail directly.
          notification.error({ title: 'Не удалось связать', description: msg });
        },
      },
    );
  };

  return (
    <Modal
      title="Связать идею с Jira-задачей"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={link.isPending}
      destroyOnHidden
      okText="Связать"
    >
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="Локальные оценки часов, impact и risk будут заменены значениями из Jira."
      />
      <Form form={form} layout="vertical" onFinish={handleSubmit}>
        <Form.Item
          name="jira_key"
          label="Jira key"
          rules={[
            { required: true, message: 'Укажите ключ задачи' },
            {
              pattern: /^[A-Za-z][A-Za-z0-9_]*-\d+$/,
              message: 'Формат: RFA-123',
            },
          ]}
        >
          <Input placeholder="Например: RFA-123" autoFocus />
        </Form.Item>
      </Form>
    </Modal>
  );
}
