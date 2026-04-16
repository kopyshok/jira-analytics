import { useState } from 'react';
import { Tabs, Table, Button, Space, Popconfirm, App, DatePicker, InputNumber, Select, Form, Modal } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import { useTeamCapacity, useVacations, useAddVacation, useRemoveVacation, useCapacityRules, useAddCapacityRule, useRemoveCapacityRule, useEmployees } from '../hooks/useCapacity';
import { useQuarterYear } from '../hooks/useQuarterYear';
import { formatHours } from '../utils/format';
import { QUARTER_MONTHS, MONTH_NAMES } from '../utils/constants';
import type { QuarterCapacityResponse, VacationResponse, CapacityRuleResponse } from '../types/api';

function TeamTab() {
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useTeamCapacity(year, quarter);
  const months = QUARTER_MONTHS[Number(quarter)] || [];

  const columns = [
    { title: 'Сотрудник', dataIndex: 'employee_name', fixed: 'left' as const, width: 200 },
    ...months.map((m) => ({
      title: MONTH_NAMES[m],
      key: `m${m}`,
      render: (_: unknown, r: QuarterCapacityResponse) => {
        const mc = r.months.find((x) => x.month === m);
        return mc ? formatHours(mc.available_hours) : '—';
      },
    })),
    { title: 'Итого', dataIndex: 'total_available_hours', render: formatHours },
  ];

  return <Table<QuarterCapacityResponse> dataSource={data} rowKey="employee_id" loading={isLoading} columns={columns} pagination={false} size="small" scroll={{ x: 800 }} />;
}

function VacationsTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useVacations();
  const { data: employees } = useEmployees();
  const add = useAddVacation();
  const remove = useRemoveVacation();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const employeeMap = new Map(employees?.map((e) => [e.id, e.display_name]));

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>Добавить отпуск</Button>
      <Modal title="Новый отпуск" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={add.isPending}>
        <Form form={form} layout="vertical" onFinish={(vals) => {
          add.mutate({
            employee_id: vals.employee_id,
            start_date: vals.dates[0].format('YYYY-MM-DD'),
            end_date: vals.dates[1].format('YYYY-MM-DD'),
          }, {
            onSuccess: () => { setOpen(false); form.resetFields(); notification.success({ message: 'Отпуск добавлен' }); },
            onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
          });
        }}>
          <Form.Item name="employee_id" label="Сотрудник" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={employees?.map((e) => ({ value: e.id, label: e.display_name }))} />
          </Form.Item>
          <Form.Item name="dates" label="Даты" rules={[{ required: true }]}>
            <DatePicker.RangePicker format="DD.MM.YYYY" />
          </Form.Item>
        </Form>
      </Modal>
      <Table<VacationResponse>
        dataSource={data}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Сотрудник', dataIndex: 'employee_id', render: (id: string) => employeeMap.get(id) || id },
          { title: 'Начало', dataIndex: 'start_date', render: (v: string) => dayjs(v).format('DD.MM.YYYY') },
          { title: 'Окончание', dataIndex: 'end_date', render: (v: string) => dayjs(v).format('DD.MM.YYYY') },
          { title: 'Часов', dataIndex: 'hours_total', render: (v: number | null) => v != null ? formatHours(v) : '—' },
          {
            title: '', width: 50,
            render: (_, r) => (
              <Popconfirm title="Удалить?" onConfirm={() => remove.mutate(r.id)}>
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}

function RulesTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useCapacityRules();
  const add = useAddCapacityRule();
  const remove = useRemoveCapacityRule();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>Добавить правило</Button>
      <Modal title="Новое правило ёмкости" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={add.isPending}>
        <Form form={form} layout="vertical" onFinish={(vals) => {
          add.mutate(vals, {
            onSuccess: () => { setOpen(false); form.resetFields(); notification.success({ message: 'Правило добавлено' }); },
            onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
          });
        }}>
          <Form.Item name="year" label="Год" rules={[{ required: true }]} initialValue={new Date().getFullYear()}>
            <InputNumber min={2020} max={2030} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="month" label="Месяц" rules={[{ required: true }]}>
            <Select options={Object.entries(MONTH_NAMES).map(([v, l]) => ({ value: Number(v), label: l }))} />
          </Form.Item>
          <Form.Item name="percent_of_norm" label="% от нормы" rules={[{ required: true }]} initialValue={10}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
      <Table<CapacityRuleResponse>
        dataSource={data}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Год', dataIndex: 'year' },
          { title: 'Месяц', dataIndex: 'month', render: (v: number) => MONTH_NAMES[v] || v },
          { title: '% от нормы', dataIndex: 'percent_of_norm', render: (v: number) => `${v}%` },
          {
            title: '', width: 50,
            render: (_, r) => (
              <Popconfirm title="Удалить?" onConfirm={() => remove.mutate(r.id)}>
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}

export default function CapacityPage() {
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <QuarterYearSelect />
      <Tabs items={[
        { key: 'team', label: 'Команда', children: <TeamTab /> },
        { key: 'vacations', label: 'Отпуска', children: <VacationsTab /> },
        { key: 'rules', label: 'Правила', children: <RulesTab /> },
      ]} />
    </Space>
  );
}
