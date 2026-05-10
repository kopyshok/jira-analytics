import { App, Button, DatePicker, Form, Input, Modal, Popconfirm, Select, Table } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ScheduledBlock } from '../../api/resourcePlanning';
import {
  useScheduledBlocks, useCreateScheduledBlock, useDeleteScheduledBlock,
} from '../../hooks/useResourcePlanning';
import { useRoles } from '../../hooks/useRoles';

interface Props {
  open: boolean;
  onClose: () => void;
  team?: string;
}

export default function ScheduledBlocksModal({ open, onClose, team }: Props) {
  const { message } = App.useApp();
  const { data: blocks = [] } = useScheduledBlocks(team);
  const { data: roles = [] } = useRoles();
  const createBlock = useCreateScheduledBlock();
  const deleteBlock = useDeleteScheduledBlock();
  const [form] = Form.useForm();

  const onFinish = async (values: Record<string, unknown>) => {
    try {
      const dates = values.dates as [dayjs.Dayjs, dayjs.Dayjs];
      const roleId = (values.role_id as string | undefined) ?? null;
      await createBlock.mutateAsync({
        team: team ?? null,
        role_ids: roleId ? [roleId] : [],
        employee_ids: [],
        start_date: dates[0].format('YYYY-MM-DD'),
        end_date: dates[1].format('YYYY-MM-DD'),
        reason: values.reason as string,
      });
      form.resetFields();
      message.success('Период добавлен');
    } catch {
      message.error('Ошибка сохранения');
    }
  };

  const columns = [
    { title: 'Начало', dataIndex: 'start_date', width: 100 },
    { title: 'Конец', dataIndex: 'end_date', width: 100 },
    { title: 'Причина', dataIndex: 'reason', ellipsis: true },
    {
      title: '',
      width: 40,
      render: (_: unknown, r: ScheduledBlock) => (
        <Popconfirm title="Удалить?" onConfirm={() => deleteBlock.mutate(r.id)}>
          <Button size="small" icon={<DeleteOutlined />} danger type="text" />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Modal title="Заблокированные периоды" open={open} onCancel={onClose} footer={null} width={600}>
      <Form form={form} layout="inline" onFinish={onFinish} style={{ marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Form.Item name="dates" rules={[{ required: true, message: 'Выберите даты' }]}>
          <DatePicker.RangePicker size="small" format="DD.MM.YYYY" />
        </Form.Item>
        <Form.Item name="role_id">
          <Select size="small" placeholder="Роль (необяз.)" allowClear style={{ width: 140 }}
            options={roles.map((r: { id: string; label: string }) => ({ label: r.label, value: r.id }))} />
        </Form.Item>
        <Form.Item name="reason" rules={[{ required: true, message: 'Укажите причину' }]}>
          <Input size="small" placeholder="Причина" style={{ width: 160 }} />
        </Form.Item>
        <Form.Item>
          <Button size="small" type="primary" htmlType="submit" icon={<PlusOutlined />}>Добавить</Button>
        </Form.Item>
      </Form>
      <Table dataSource={blocks} columns={columns} rowKey="id" size="small" pagination={false} />
    </Modal>
  );
}
