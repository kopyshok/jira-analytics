import { useEffect } from 'react';
import { App, Modal, Form, Input, InputNumber, Select } from 'antd';
import { useCreateBacklogItem, useUpdateBacklogItem, useProjects } from '../../hooks/useBacklog';
import { useQuarterYear } from '../../hooks/useQuarterYear';
import type { BacklogItemResponse, BacklogImpactRisk } from '../../types/api';

interface Props {
  open: boolean;
  item?: BacklogItemResponse | null;
  onClose: () => void;
}

interface FormValues {
  title: string;
  project_id?: string;
  year?: number;
  quarter?: string;
  priority?: number;
  estimate_analyst_hours?: number;
  estimate_dev_hours?: number;
  estimate_qa_hours?: number;
  estimate_opo_hours?: number;
  opo_analyst_ratio?: number;
  impact?: BacklogImpactRisk;
  risk?: BacklogImpactRisk;
}

const IMPACT_RISK_OPTIONS = [
  { value: 'low', label: 'Низкий' },
  { value: 'medium', label: 'Средний' },
  { value: 'high', label: 'Высокий' },
];

export default function BacklogManualModal({ open, item, onClose }: Props) {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const { data: projects } = useProjects();
  const create = useCreateBacklogItem();
  const update = useUpdateBacklogItem();
  const [form] = Form.useForm<FormValues>();

  const isEdit = !!item;

  useEffect(() => {
    if (!open) return;
    if (item) {
      form.setFieldsValue({
        title: item.title,
        project_id: item.project_id ?? undefined,
        year: item.year ?? undefined,
        quarter: item.quarter ?? undefined,
        priority: item.priority ?? undefined,
        estimate_analyst_hours: item.estimate_analyst_hours ?? undefined,
        estimate_dev_hours: item.estimate_dev_hours ?? undefined,
        estimate_qa_hours: item.estimate_qa_hours ?? undefined,
        estimate_opo_hours: item.estimate_opo_hours ?? undefined,
        opo_analyst_ratio: item.opo_analyst_ratio ?? 0.5,
        impact: item.impact ?? undefined,
        risk: item.risk ?? undefined,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        year: Number(year),
        quarter: `Q${quarter}`,
        opo_analyst_ratio: 0.5,
      });
    }
  }, [open, item, year, quarter, form]);

  const handleSubmit = (values: FormValues) => {
    const payload = {
      ...values,
      // empty-string → undefined for optional fields
      project_id: values.project_id || undefined,
      impact: values.impact || undefined,
      risk: values.risk || undefined,
    };
    if (isEdit && item) {
      update.mutate(
        { id: item.id, data: payload },
        {
          onSuccess: () => {
            notification.success({ title: 'Обновлено' });
            onClose();
          },
          onError: (e) =>
            notification.error({ title: 'Ошибка', description: (e as Error).message }),
        },
      );
    } else {
      create.mutate(payload, {
        onSuccess: () => {
          notification.success({ title: 'Создано' });
          onClose();
        },
        onError: (e) =>
          notification.error({ title: 'Ошибка', description: (e as Error).message }),
      });
    }
  };

  return (
    <Modal
      title={isEdit ? 'Редактирование идеи' : 'Новая идея'}
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={create.isPending || update.isPending}
      destroyOnHidden
      width={560}
    >
      <Form form={form} layout="vertical" onFinish={handleSubmit}>
        <Form.Item name="title" label="Название" rules={[{ required: true, message: 'Укажите название' }]}>
          <Input placeholder="Например: Миграция на новую версию API" />
        </Form.Item>

        <Form.Item name="project_id" label="Проект">
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="Выберите проект"
            options={projects?.map((p) => ({ value: p.id, label: `${p.key} — ${p.name}` }))}
          />
        </Form.Item>

        <Form.Item label="Период" style={{ marginBottom: 0 }}>
          <Form.Item
            name="year"
            label="Год"
            style={{ display: 'inline-block', width: 'calc(50% - 8px)', marginRight: 16 }}
            rules={[{ required: true, message: 'Год' }]}
          >
            <InputNumber min={2020} max={2035} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="quarter"
            label="Квартал"
            style={{ display: 'inline-block', width: 'calc(50% - 8px)' }}
            rules={[{ required: true, message: 'Квартал' }]}
          >
            <Select
              options={[
                { value: 'Q1', label: 'Q1' },
                { value: 'Q2', label: 'Q2' },
                { value: 'Q3', label: 'Q3' },
                { value: 'Q4', label: 'Q4' },
              ]}
            />
          </Form.Item>
        </Form.Item>

        <Form.Item label="Оценка по ролям (часы)" style={{ marginBottom: 0 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
            <Form.Item name="estimate_analyst_hours" label="АН ч">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="estimate_dev_hours" label="ПР ч">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="estimate_qa_hours" label="ТС ч">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="estimate_opo_hours" label="ОПЭ ч">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </div>
        </Form.Item>

        <Form.Item
          name="opo_analyst_ratio"
          label="Доля ОПЭ на аналитика (0…1)"
          tooltip="Какая часть часов ОПЭ ложится на АН; остальное — на ПР"
        >
          <InputNumber min={0} max={1} step={0.05} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item label="Приоритизация" style={{ marginBottom: 0 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <Form.Item name="priority" label="Приоритет">
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="impact" label="Impact">
              <Select allowClear options={IMPACT_RISK_OPTIONS} />
            </Form.Item>
            <Form.Item name="risk" label="Risk">
              <Select allowClear options={IMPACT_RISK_OPTIONS} />
            </Form.Item>
          </div>
        </Form.Item>
      </Form>
    </Modal>
  );
}
