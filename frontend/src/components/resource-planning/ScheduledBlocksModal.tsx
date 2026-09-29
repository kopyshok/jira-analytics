import { App, Button, DatePicker, Form, Input, Modal, Popconfirm, Select, Table, Typography } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { useMemo, useState } from 'react';
import dayjs from 'dayjs';
import type { ScheduledBlock, ScheduledBlockInput } from '../../api/resourcePlanning';
import {
  useScheduledBlocks, useCreateScheduledBlock, useUpdateScheduledBlock, useDeleteScheduledBlock,
} from '../../hooks/useResourcePlanning';
import { useRoles } from '../../hooks/useRoles';
import { useMandatoryWorkTypes } from '../../hooks/useCapacity';
import { blockAudience, notAppliedText } from '../../utils/scheduledBlocks';

interface Props {
  open: boolean;
  onClose: () => void;
  team?: string;
  /** Состав команды — для выбора конкретных сотрудников периода. */
  members?: { id: string; name: string }[];
}

interface FormValues {
  dates: [dayjs.Dayjs, dayjs.Dayjs];
  work_type_id: string;
  role_ids?: string[];
  employee_ids?: string[];
  reason: string;
}

export default function ScheduledBlocksModal({ open, onClose, team, members = [] }: Props) {
  const { message } = App.useApp();
  const { data: blocks = [] } = useScheduledBlocks(team);
  const { data: roles = [] } = useRoles();
  const { data: workTypes = [] } = useMandatoryWorkTypes({ isActive: true });
  const workTypeOptions = workTypes
    .filter(w => w.subtracts_from_pool)
    .map(w => ({ label: w.label, value: w.id }));
  const createBlock = useCreateScheduledBlock();
  const updateBlock = useUpdateScheduledBlock();
  const deleteBlock = useDeleteScheduledBlock();
  const [form] = Form.useForm<FormValues>();
  const [editingId, setEditingId] = useState<string | null>(null);
  const editingRow = editingId ? blocks.find(b => b.id === editingId) : undefined;

  // При редактировании сотрудник/вид работ периода может отсутствовать в текущих
  // активных справочниках — добавляем их в опции, чтобы select не показывал raw id.
  const employeeOptions = useMemo(() => {
    const base = members.map(m => ({ label: m.name, value: m.id }));
    if (!editingRow) return base;
    const known = new Set(members.map(m => m.id));
    const missing = editingRow.employee_ids.filter(id => !known.has(id));
    return [...base, ...missing.map(id => ({ label: 'сотрудник не в составе', value: id }))];
  }, [members, editingRow]);

  const workTypeOptionsForForm = useMemo(() => {
    if (!editingRow?.work_type_id) return workTypeOptions;
    if (workTypeOptions.some(o => o.value === editingRow.work_type_id)) return workTypeOptions;
    return [
      ...workTypeOptions,
      { label: editingRow.work_type_label ?? 'вид работ не найден', value: editingRow.work_type_id },
    ];
  }, [workTypeOptions, editingRow]);

  const cancelEdit = () => {
    setEditingId(null);
    form.resetFields();
  };

  const onFinish = async (values: FormValues) => {
    const base = {
      role_ids: values.role_ids ?? [],
      employee_ids: values.employee_ids ?? [],
      start_date: values.dates[0].format('YYYY-MM-DD'),
      end_date: values.dates[1].format('YYYY-MM-DD'),
      reason: values.reason,
      work_type_id: values.work_type_id,
    };
    try {
      if (editingId) {
        // Команду периода при редактировании не трогаем: модалка может быть открыта
        // без выбранной команды (тогда team тут undefined) и без team в payload
        // затёрла бы команду периода на null.
        await updateBlock.mutateAsync({ id: editingId, data: base });
        message.success('Период сохранён');
      } else {
        const data: ScheduledBlockInput = { ...base, team: team ?? null };
        await createBlock.mutateAsync(data);
        message.success('Период добавлен');
      }
      cancelEdit();
    } catch (e) {
      message.error((e as Error).message || 'Ошибка сохранения');
    }
  };

  const startEdit = (r: ScheduledBlock) => {
    setEditingId(r.id);
    form.setFieldsValue({
      dates: [dayjs(r.start_date), dayjs(r.end_date)],
      work_type_id: r.work_type_id ?? undefined,
      role_ids: r.role_ids,
      employee_ids: r.employee_ids,
      reason: r.reason,
    });
  };

  const columns = [
    {
      title: 'Даты',
      width: 110,
      render: (_: unknown, r: ScheduledBlock) =>
        `${dayjs(r.start_date).format('DD.MM')}–${dayjs(r.end_date).format('DD.MM')}`,
    },
    {
      title: 'Кому',
      render: (_: unknown, r: ScheduledBlock) => (
        <>
          {blockAudience(r)}
          {notAppliedText(r) && (
            <Typography.Text type="warning" style={{ display: 'block', fontSize: 12 }}>
              {notAppliedText(r)}
            </Typography.Text>
          )}
        </>
      ),
    },
    {
      title: 'Вид работ',
      render: (_: unknown, r: ScheduledBlock) =>
        r.work_type_label ?? <Typography.Text type="danger">укажите вид работ</Typography.Text>,
    },
    { title: 'Причина', dataIndex: 'reason', ellipsis: true },
    {
      title: '',
      width: 70,
      render: (_: unknown, r: ScheduledBlock) => (
        <>
          <Button size="small" icon={<EditOutlined />} type="text" onClick={() => startEdit(r)} />
          <Popconfirm title="Удалить?" onConfirm={() => deleteBlock.mutate(r.id)}>
            <Button size="small" icon={<DeleteOutlined />} danger type="text" />
          </Popconfirm>
        </>
      ),
    },
  ];

  return (
    <Modal
      title="Заблокированные периоды"
      open={open}
      onCancel={onClose}
      afterClose={cancelEdit}
      footer={null}
      width={820}
    >
      <Form form={form} layout="inline" onFinish={onFinish} style={{ marginBottom: 4, flexWrap: 'wrap', gap: 8 }}>
        <Form.Item name="dates" rules={[{ required: true, message: 'Выберите даты' }]}>
          <DatePicker.RangePicker size="small" format="DD.MM.YYYY" />
        </Form.Item>
        <Form.Item name="work_type_id" rules={[{ required: true, message: 'Выберите вид работ' }]}>
          <Select size="small" placeholder="Вид работ" style={{ width: 180 }} options={workTypeOptionsForForm} />
        </Form.Item>
        <Form.Item name="role_ids">
          <Select
            size="small"
            mode="multiple"
            placeholder="Роли (необяз.)"
            allowClear
            style={{ width: 160 }}
            options={roles.map((r: { id: string; label: string }) => ({ label: r.label, value: r.id }))}
          />
        </Form.Item>
        <Form.Item name="employee_ids">
          <Select
            size="small"
            mode="multiple"
            placeholder="Сотрудники (необяз.)"
            allowClear
            optionFilterProp="label"
            style={{ width: 180 }}
            options={employeeOptions}
          />
        </Form.Item>
        <Form.Item name="reason" rules={[{ required: true, message: 'Укажите причину' }]}>
          <Input size="small" placeholder="Причина" style={{ width: 160 }} />
        </Form.Item>
        <Form.Item>
          <Button size="small" type="primary" htmlType="submit" icon={editingId ? undefined : <PlusOutlined />}>
            {editingId ? 'Сохранить' : 'Добавить'}
          </Button>
        </Form.Item>
        {editingId && (
          <Form.Item>
            <Button size="small" onClick={cancelEdit}>Отмена</Button>
          </Form.Item>
        )}
      </Form>
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
        Не выбраны роли и сотрудники — период для всей команды. В одном месяце и виде работ действует
        самый точный период: сотрудника главнее роли, роль главнее команды — даже если даты не совпадают.
        Для разового события (обучение, весь месяц) выберите другой вид работ.
      </Typography.Text>
      <Table dataSource={blocks} columns={columns} rowKey="id" size="small" pagination={false} />
    </Modal>
  );
}
