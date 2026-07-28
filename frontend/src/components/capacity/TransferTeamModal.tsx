import { Modal, Form, Select, DatePicker, Typography, App } from 'antd';
import dayjs, { Dayjs } from 'dayjs';

import { useTransferEmployeeTeam } from '../../hooks/useCapacity';

const { Text } = Typography;

interface Props {
  open: boolean;
  employeeId: string;
  fromTeam: string;
  availableTeams: string[];
  onClose: () => void;
}

export default function TransferTeamModal({
  open, employeeId, fromTeam, availableTeams, onClose,
}: Props) {
  const { message } = App.useApp();
  const [form] = Form.useForm<{ to_team: string; on: Dayjs }>();
  const transfer = useTransferEmployeeTeam();

  const handleOk = async () => {
    const values = await form.validateFields();
    try {
      await transfer.mutateAsync({
        employeeId,
        from_team: fromTeam,
        to_team: values.to_team,
        on: values.on.format('YYYY-MM-DD'),
      });
      message.success('Сотрудник переведён');
      form.resetFields();
      onClose();
    } catch {
      message.error('Не удалось перевести');
    }
  };

  return (
    <Modal
      open={open}
      title={`Перевести из команды «${fromTeam}»`}
      onOk={handleOk}
      onCancel={onClose}
      okText="Перевести"
      cancelText="Отмена"
      confirmLoading={transfer.isPending}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" initialValues={{ on: dayjs() }}>
        <Form.Item
          name="to_team"
          label="Новая команда"
          rules={[{ required: true, message: 'Выберите команду' }]}
        >
          <Select
            showSearch
            placeholder="Команда"
            options={availableTeams
              .filter((t) => t !== fromTeam)
              .map((t) => ({ value: t, label: t }))}
          />
        </Form.Item>
        <Form.Item
          name="on"
          label="Дата перевода"
          rules={[{ required: true, message: 'Укажите дату' }]}
        >
          <DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} />
        </Form.Item>
        <Text type="secondary">
          Участие в прежней команде закроется этой датой, новое откроется с неё же.
          Часы квартала пересчитаются автоматически.
        </Text>
      </Form>
    </Modal>
  );
}
