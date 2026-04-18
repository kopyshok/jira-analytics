import { useState, useEffect } from 'react';
import { Tabs, Table, Button, Space, Popconfirm, App, DatePicker, InputNumber, Select, Form, Modal, AutoComplete, Typography } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import { useTeamCapacity, useVacations, useAddVacation, useRemoveVacation, useCapacityRules, useAddCapacityRule, useRemoveCapacityRule, useEmployees, useRecalcActiveEmployees, useSearchJiraUsers, useAddEmployeeFromJira } from '../hooks/useCapacity';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useQuarterYear } from '../hooks/useQuarterYear';
import { formatHours } from '../utils/format';
import { QUARTER_MONTHS, MONTH_NAMES } from '../utils/constants';
import type { QuarterCapacityResponse, VacationResponse, CapacityRuleResponse, JiraUserSearchResult } from '../types/api';

const { Text } = Typography;

function TeamTab() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useTeamCapacity(year, quarter);
  const { data: employees } = useEmployees();
  const recalc = useRecalcActiveEmployees();

  const stored = useGenericSetting('ui_capacity_team_filter');
  const saveStored = useSaveGenericSetting();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated || stored.data === undefined) return;
    const val = stored.data?.value;
    if (val) setSelectedIds(val.split(',').filter(Boolean));
    setHydrated(true);
  }, [hydrated, stored.data]);

  useEffect(() => {
    if (!hydrated || !employees || selectedIds.length === 0) return;
    const activeIds = new Set(employees.filter(e => e.is_active).map(e => e.id));
    const filtered = selectedIds.filter(id => activeIds.has(id));
    if (filtered.length !== selectedIds.length) {
      setSelectedIds(filtered);
      saveStored.mutate({ key: 'ui_capacity_team_filter', value: filtered.join(',') });
    }
  }, [hydrated, employees, selectedIds, saveStored]);

  const handleFilterChange = (val: string[]) => {
    setSelectedIds(val);
    saveStored.mutate({ key: 'ui_capacity_team_filter', value: val.join(',') });
  };

  const [addOpen, setAddOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  const searchRes = useSearchJiraUsers(debouncedQuery);
  const addMut = useAddEmployeeFromJira();

  const handlePick = (user: JiraUserSearchResult) => {
    addMut.mutate({
      jira_account_id: user.jira_account_id,
      display_name: user.display_name,
      email: user.email,
      is_active: true,
      avatar_url: user.avatar_url,
    }, {
      onSuccess: () => {
        notification.success({ title: `Добавлен: ${user.display_name}` });
        setAddOpen(false);
        setQuery('');
      },
      onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
    });
  };

  const months = QUARTER_MONTHS[Number(quarter)] || [];
  const visibleData = selectedIds.length === 0
    ? data
    : data?.filter(r => selectedIds.includes(r.employee_id));

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

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Select
          mode="multiple"
          allowClear
          placeholder="Фильтр по сотруднику"
          style={{ minWidth: 260 }}
          value={selectedIds}
          onChange={handleFilterChange}
          showSearch
          optionFilterProp="label"
          options={(employees ?? [])
            .filter(e => e.is_active)
            .map(e => ({ value: e.id, label: e.display_name }))}
        />
        <Popconfirm
          title="Пересчитать состав по worklog'ам активных задач?"
          okText="Пересчитать"
          cancelText="Отмена"
          okButtonProps={{ danger: true }}
          onConfirm={() => recalc.mutate(undefined, {
            onSuccess: (s) => notification.success({
              title: 'Состав обновлён',
              description: `Активировано: ${s.activated}, деактивировано: ${s.deactivated}, всего активных: ${s.total_active}`,
            }),
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          })}
        >
          <Button loading={recalc.isPending}>Пересчитать состав</Button>
        </Popconfirm>
        <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
          Добавить сотрудника
        </Button>
      </Space>
      <Table<QuarterCapacityResponse>
        dataSource={visibleData}
        rowKey="employee_id"
        loading={isLoading}
        columns={columns}
        pagination={false}
        size="small"
        scroll={{ x: 800 }}
      />
      <Modal
        title="Добавить сотрудника из Jira"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        footer={null}
      >
        <AutoComplete
          style={{ width: '100%' }}
          value={query}
          onChange={setQuery}
          placeholder="Имя или e-mail (от 2 символов)"
          options={(searchRes.data ?? []).map(u => ({
            value: u.jira_account_id,
            label: `${u.display_name}${u.email ? ` · ${u.email}` : ''}`,
            user: u,
          }))}
          onSelect={(_, opt) => handlePick((opt as { user: JiraUserSearchResult }).user)}
        />
        {searchRes.isFetching && <Text type="secondary">Ищу…</Text>}
      </Modal>
    </Space>
  );
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
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>Добавить отпуск</Button>
      <Modal title="Новый отпуск" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={add.isPending}>
        <Form form={form} layout="vertical" onFinish={(vals) => {
          add.mutate({
            employee_id: vals.employee_id,
            start_date: vals.dates[0].format('YYYY-MM-DD'),
            end_date: vals.dates[1].format('YYYY-MM-DD'),
          }, {
            onSuccess: () => { setOpen(false); form.resetFields(); notification.success({ title: 'Отпуск добавлен' }); },
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
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
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>Добавить правило</Button>
      <Modal title="Новое правило ёмкости" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={add.isPending}>
        <Form form={form} layout="vertical" onFinish={(vals) => {
          add.mutate(vals, {
            onSuccess: () => { setOpen(false); form.resetFields(); notification.success({ title: 'Правило добавлено' }); },
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
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
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <QuarterYearSelect />
      <Tabs items={[
        { key: 'team', label: 'Команда', children: <TeamTab /> },
        { key: 'vacations', label: 'Отпуска', children: <VacationsTab /> },
        { key: 'rules', label: 'Правила', children: <RulesTab /> },
      ]} />
    </Space>
  );
}
