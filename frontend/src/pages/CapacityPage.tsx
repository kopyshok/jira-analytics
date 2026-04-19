import { useState, useEffect } from 'react';
import { Tabs, Table, Button, Space, Popconfirm, App, DatePicker, InputNumber, Select, Form, Modal, AutoComplete, Typography } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import PageHeader from '../components/shared/PageHeader';
import { useTeamCapacity, useCapacityRules, useAddCapacityRule, useRemoveCapacityRule, useEmployees, useRecalcActiveEmployees, useSearchJiraUsers, useAddEmployeeFromJira, useCategoryBreakdown } from '../hooks/useCapacity';
import { useAbsences, useAddAbsence, useRemoveAbsence } from '../hooks/useAbsences';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useQuarterYear } from '../hooks/useQuarterYear';
import { formatHours } from '../utils/format';
import { QUARTER_MONTHS, MONTH_NAMES } from '../utils/constants';
import type { QuarterCapacityResponse, AbsenceResponse, AbsenceReason, CapacityRuleResponse, JiraUserSearchResult, CategoryBreakdownResponse } from '../types/api';

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

  const pctColor = (plan: number, fact: number): string | undefined => {
    if (plan <= 0) return undefined;
    const pct = (fact / plan) * 100;
    if (pct >= 100) return 'var(--ant-color-success, #52c41a)';
    if (pct < 50) return 'var(--ant-color-text-secondary, #999)';
    return undefined;
  };

  const pctText = (plan: number, fact: number): string => {
    if (plan <= 0) return '—';
    return `${Math.round((fact / plan) * 100)}%`;
  };

  const monthGroup = (m: number) => ({
    title: MONTH_NAMES[m],
    children: [
      {
        title: 'План',
        key: `m${m}_plan`,
        width: 80,
        render: (_: unknown, r: QuarterCapacityResponse) => {
          const mc = r.months.find((x) => x.month === m);
          return mc ? formatHours(mc.available_hours) : '—';
        },
      },
      {
        title: 'Факт',
        key: `m${m}_fact`,
        width: 80,
        render: (_: unknown, r: QuarterCapacityResponse) => {
          const mc = r.months.find((x) => x.month === m);
          return mc ? formatHours(mc.fact_hours) : '—';
        },
      },
      {
        title: '%',
        key: `m${m}_pct`,
        width: 60,
        render: (_: unknown, r: QuarterCapacityResponse) => {
          const mc = r.months.find((x) => x.month === m);
          if (!mc) return '—';
          return (
            <span style={{ color: pctColor(mc.available_hours, mc.fact_hours) }}>
              {pctText(mc.available_hours, mc.fact_hours)}
            </span>
          );
        },
      },
    ],
  });

  const columns = [
    { title: 'Сотрудник', dataIndex: 'employee_name', fixed: 'left' as const, width: 200 },
    ...months.map(monthGroup),
    {
      title: 'Итого',
      children: [
        { title: 'План', dataIndex: 'total_available_hours', render: formatHours, width: 90 },
        { title: 'Факт', dataIndex: 'total_fact_hours', render: formatHours, width: 90 },
        {
          title: '%', width: 70,
          render: (_: unknown, r: QuarterCapacityResponse) => (
            <span style={{ color: pctColor(r.total_available_hours, r.total_fact_hours) }}>
              {pctText(r.total_available_hours, r.total_fact_hours)}
            </span>
          ),
        },
      ],
    },
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
        scroll={{ x: 1400 }}
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

const REASON_OPTIONS: { value: AbsenceReason; label: string; color: string }[] = [
  { value: 'vacation', label: 'Отпуск',     color: '#fa8c16' },
  { value: 'sick',     label: 'Больничный', color: '#f5222d' },
  { value: 'day_off',  label: 'Отгул',      color: '#1677ff' },
  { value: 'other',    label: 'Прочее',     color: '#8c8c8c' },
];

function reasonMeta(r: AbsenceReason) {
  return REASON_OPTIONS.find(o => o.value === r) ?? REASON_OPTIONS[0];
}

function AbsencesTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useAbsences();
  const { data: employees } = useEmployees();
  const add = useAddAbsence();
  const remove = useRemoveAbsence();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const employeeMap = new Map(employees?.map((e) => [e.id, e.display_name]));

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      {/* Heatmap placeholder — Task 5.3 adds AbsenceHeatmap here */}
      <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>
        Добавить отсутствие
      </Button>
      <Modal
        title="Новое отсутствие"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={add.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ reason: 'vacation' }}
          onFinish={(vals) => {
            add.mutate(
              {
                employee_id: vals.employee_id,
                start_date: vals.dates[0].format('YYYY-MM-DD'),
                end_date: vals.dates[1].format('YYYY-MM-DD'),
                reason: vals.reason,
              },
              {
                onSuccess: () => {
                  setOpen(false);
                  form.resetFields();
                  notification.success({ title: 'Отсутствие добавлено' });
                },
                onError: (e) =>
                  notification.error({ title: 'Ошибка', description: e.message }),
              },
            );
          }}
        >
          <Form.Item name="employee_id" label="Сотрудник" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label"
              options={employees?.map((e) => ({ value: e.id, label: e.display_name }))} />
          </Form.Item>
          <Form.Item name="reason" label="Причина" rules={[{ required: true }]}>
            <Select options={REASON_OPTIONS.map(o => ({ value: o.value, label: o.label }))} />
          </Form.Item>
          <Form.Item name="dates" label="Даты" rules={[{ required: true }]}>
            <DatePicker.RangePicker format="DD.MM.YYYY" />
          </Form.Item>
        </Form>
      </Modal>
      <Table<AbsenceResponse>
        dataSource={data}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Сотрудник', dataIndex: 'employee_id',
            render: (id: string) => employeeMap.get(id) || id },
          { title: 'Причина', dataIndex: 'reason', width: 130,
            render: (v: AbsenceReason) => {
              const m = reasonMeta(v);
              return <span style={{ color: m.color }}>{m.label}</span>;
            },
          },
          { title: 'Начало', dataIndex: 'start_date',
            render: (v: string) => dayjs(v).format('DD.MM.YYYY') },
          { title: 'Окончание', dataIndex: 'end_date',
            render: (v: string) => dayjs(v).format('DD.MM.YYYY') },
          { title: 'Часов', dataIndex: 'hours_total',
            render: (v: number | null) => v != null ? formatHours(v) : '—' },
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

function BreakdownTab() {
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useCategoryBreakdown(Number(year), Number(quarter));
  return (
    <Table<CategoryBreakdownResponse>
      dataSource={data}
      rowKey="employee_id"
      loading={isLoading}
      pagination={false}
      size="small"
      columns={[
        { title: 'Сотрудник', dataIndex: 'employee_name', fixed: 'left' as const, width: 200 },
        { title: 'Активный стек',
          render: (_, r: CategoryBreakdownResponse) => formatHours(r.by_bucket.active_stack) },
        { title: 'Инициативы',
          render: (_, r: CategoryBreakdownResponse) => formatHours(r.by_bucket.initiatives) },
        { title: 'Архив квартальных',
          render: (_, r: CategoryBreakdownResponse) => formatHours(r.by_bucket.archive_target) },
        { title: 'Архив прочих',
          render: (_, r: CategoryBreakdownResponse) => formatHours(r.by_bucket.archive_other) },
        { title: 'Без категории',
          render: (_, r: CategoryBreakdownResponse) => formatHours(r.by_bucket.uncategorized) },
        { title: 'Итого', dataIndex: 'total_hours', render: formatHours },
      ]}
    />
  );
}

export default function CapacityPage() {
  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader
        eyebrow="Планирование"
        title="Ресурсы команды"
        subtitle="План · факт · отпуска · правила обязательной загрузки"
        actions={<QuarterYearSelect />}
      />
      <Tabs items={[
        { key: 'team', label: 'Команда', children: <TeamTab /> },
        { key: 'breakdown', label: 'Распределение', children: <BreakdownTab /> },
        { key: 'absences', label: 'Отсутствия', children: <AbsencesTab /> },
        { key: 'rules', label: 'Правила', children: <RulesTab /> },
      ]} />
    </Space>
  );
}
