import { useEffect } from 'react';
import { App, Form, Input, InputNumber, Modal, Select } from 'antd';
import { useCreateScenario } from '../../hooks/usePlanning';
import { useQuarterYear } from '../../hooks/useQuarterYear';
import { TeamSelector } from './TeamSelector';
import { trackAction } from '../../lib/usage/track';

interface Props {
  open: boolean;
  onClose: (createdId?: string) => void;
}

interface FormValues {
  name: string;
  year: number;
  quarter: number;
  team: string;
}

/** Обёртка-переходник: AntD Form.Item передаёт value/onChange как необязательные,
 *  но TeamSelector объявляет их обязательными — этот компонент устраняет несоответствие. */
function TeamSelectorFormItem(props: { value?: string | null; onChange?: (v: string | null) => void; style?: React.CSSProperties }) {
  return (
    <TeamSelector
      value={props.value ?? null}
      onChange={props.onChange ?? (() => undefined)}
      style={props.style}
    />
  );
}

/** Модалка создания draft-сценария: name + year + quarter + team. После успеха
 *  родитель получает id через onClose(id) и переключает выбор. */
export default function ScenarioCreateModal({ open, onClose }: Props) {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const create = useCreateScenario();
  const [form] = Form.useForm<FormValues>();
  // Derived: пересчёт disabled идёт от актуальных полей формы, без setState-in-effect.
  const values = Form.useWatch([], form) as Partial<FormValues> | undefined;
  const submitDisabled = !values?.name || !values?.year || !values?.quarter || !values?.team;

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    form.setFieldsValue({
      year: Number(year),
      quarter: Number(quarter),
      name: `Q${quarter} ${year} plan`,
    });
  }, [open, year, quarter, form]);

  const handleSubmit = (values: FormValues) => {
    create.mutate(values, {
      onSuccess: (s) => {
        trackAction('scenario_created', s.id);
        notification.success({ title: `Сценарий «${s.name}» создан` });
        onClose(s.id);
      },
      onError: (e) =>
        notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  return (
    <Modal
      title="Новый сценарий квартала"
      open={open}
      onCancel={() => onClose()}
      onOk={() => form.submit()}
      confirmLoading={create.isPending}
      okButtonProps={{ disabled: submitDisabled }}
      destroyOnHidden
      width={460}
      okText="Создать"
      cancelText="Отмена"
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
      >
        <Form.Item
          name="name"
          label="Название"
          rules={[{ required: true, message: 'Укажите название' }]}
        >
          <Input placeholder="Например: Q2 2026 план" />
        </Form.Item>
        <Form.Item label="Период" style={{ marginBottom: 0 }}>
          <Form.Item
            name="year"
            label="Год"
            style={{ display: 'inline-block', width: 'calc(50% - 8px)', marginRight: 16 }}
            rules={[{ required: true }]}
          >
            <InputNumber min={2020} max={2035} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="quarter"
            label="Квартал"
            style={{ display: 'inline-block', width: 'calc(50% - 8px)' }}
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: 1, label: 'Q1' },
                { value: 2, label: 'Q2' },
                { value: 3, label: 'Q3' },
                { value: 4, label: 'Q4' },
              ]}
            />
          </Form.Item>
        </Form.Item>
        <Form.Item
          name="team"
          label="Команда"
          rules={[{ required: true, message: 'Выберите команду' }]}
        >
          <TeamSelectorFormItem style={{ width: '100%' }} />
        </Form.Item>
        <div style={{ fontSize: 12, color: '#8faec8' }}>
          В сценарий попадут все текущие элементы бэклога. Отметьте галочками
          задачи, которые планируете взять в квартал.
        </div>
      </Form>
    </Modal>
  );
}
