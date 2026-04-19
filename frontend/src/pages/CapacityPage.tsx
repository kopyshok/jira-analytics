import { useState, useEffect, useMemo } from 'react';
import { Tabs, Table, Button, Space, Popconfirm, App, DatePicker, InputNumber, Select, Form, Modal, AutoComplete, Typography, Switch, Tag } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import PageHeader from '../components/shared/PageHeader';
import { useTeamCapacity, useCapacityRules, useAddCapacityRule, useRemoveCapacityRule, useEmployees, useRecalcActiveEmployees, useSearchJiraUsers, useAddEmployeeFromJira, useCategoryBreakdown, useAutoDetectTeams, useCopyRules, useReplaceEmployeeTeams, useSetPrimaryTeam } from '../hooks/useCapacity';
import { useJiraTeams } from '../hooks/useSync';
import { useAbsences, useAddAbsence, useRemoveAbsence } from '../hooks/useAbsences';
import AbsenceHeatmap from '../components/capacity/AbsenceHeatmap';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useQuarterYear } from '../hooks/useQuarterYear';
import { formatHours } from '../utils/format';
import { QUARTER_MONTHS, MONTH_NAMES } from '../utils/constants';
import type { QuarterCapacityResponse, AbsenceResponse, AbsenceReason, CapacityRuleResponse, JiraUserSearchResult, CategoryBreakdownResponse, EmployeeTeamItem } from '../types/api';

const { Text } = Typography;

function TeamTab() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useTeamCapacity(year, quarter);
  const { data: employees } = useEmployees();
  const recalc = useRecalcActiveEmployees();
  const replaceTeams = useReplaceEmployeeTeams();
  const setPrimary = useSetPrimaryTeam();
  const autoDetect = useAutoDetectTeams();
  const jiraTeams = useJiraTeams();
  const employeesFull = useEmployees({ withTeams: true });
  const teamsByEmpId = useMemo(() => {
    const m = new Map<string, EmployeeTeamItem[]>();
    (employeesFull.data ?? []).forEach(e => m.set(e.id, e.teams ?? []));
    return m;
  }, [employeesFull.data]);

  const teamOptions = (jiraTeams.data ?? []).map(t => ({ value: t, label: t }));

  const storedEmp = useGenericSetting('ui_capacity_team_filter');
  const storedTeams = useGenericSetting('ui_capacity_team_filter_teams');
  const storedShowFact = useGenericSetting('ui_capacity_show_fact');
  const storedShowPct  = useGenericSetting('ui_capacity_show_pct');
  const saveStored = useSaveGenericSetting();

  const [selectedEmpIds, setSelectedEmpIds] = useState<string[]>([]);
  const [selectedTeams, setSelectedTeams] = useState<string[]>([]);
  const [showFact, setShowFact] = useState(false);
  const [showPct,  setShowPct]  = useState(false);
  const [hydrated, setHydrated] = useState(false);

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

  useEffect(() => {
    if (hydrated) return;
    if (storedEmp.data === undefined || storedTeams.data === undefined
        || storedShowFact.data === undefined || storedShowPct.data === undefined) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedEmpIds((storedEmp.data?.value || '').split(',').filter(Boolean));
    setSelectedTeams((storedTeams.data?.value || '').split(',').filter(Boolean));
    setShowFact(storedShowFact.data?.value === '1');
    setShowPct(storedShowPct.data?.value === '1');
    setHydrated(true);
  }, [hydrated, storedEmp.data, storedTeams.data, storedShowFact.data, storedShowPct.data]);

  // Drop removed employees from selection (parity with old code).
  useEffect(() => {
    if (!hydrated || !employees || selectedEmpIds.length === 0) return;
    const activeIds = new Set(employees.filter(e => e.is_active).map(e => e.id));
    const filtered = selectedEmpIds.filter(id => activeIds.has(id));
    if (filtered.length !== selectedEmpIds.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedEmpIds(filtered);
      saveStored.mutate({ key: 'ui_capacity_team_filter', value: filtered.join(',') });
    }
  }, [hydrated, employees, selectedEmpIds, saveStored]);

  const persist = (key: string, value: string) => saveStored.mutate({ key, value });

  // ------------ Filter visible rows ------------
  const visible = (data ?? []).filter(r => {
    if (selectedEmpIds.length && !selectedEmpIds.includes(r.employee_id)) return false;
    if (selectedTeams.length) {
      const teamKey = r.team ?? '__none__';
      if (!selectedTeams.includes(teamKey)) return false;
    }
    return true;
  });

  // ------------ Tree grouping ------------
  interface TeamRow {
    key: string;
    isTeam: true;
    employee_id: string;
    employee_name: string;
    team: string | null;
    months: QuarterCapacityResponse['months'];
    total_available_hours: number;
    total_fact_hours: number;
    children: QuarterCapacityResponse[];
  }
  type TreeRow = QuarterCapacityResponse | TeamRow;

  const groupByTeam = (rows: QuarterCapacityResponse[]): TeamRow[] => {
    const buckets = new Map<string, QuarterCapacityResponse[]>();
    for (const r of rows) {
      const k = r.team ?? '__none__';
      const arr = buckets.get(k) ?? [];
      arr.push(r);
      buckets.set(k, arr);
    }
    const keys = Array.from(buckets.keys()).filter(k => k !== '__none__').sort();
    if (buckets.has('__none__')) keys.push('__none__');
    return keys.map(k => {
      const members = buckets.get(k)!;
      const monthSums: QuarterCapacityResponse['months'] = [];
      if (members[0]) {
        for (const m of members[0].months) {
          monthSums.push({
            ...m,
            available_hours: members.reduce((s, mem) => s + (mem.months.find(x => x.month === m.month)?.available_hours ?? 0), 0),
            fact_hours:      members.reduce((s, mem) => s + (mem.months.find(x => x.month === m.month)?.fact_hours ?? 0), 0),
          });
        }
      }
      const total_available_hours = members.reduce((s, m) => s + m.total_available_hours, 0);
      const total_fact_hours      = members.reduce((s, m) => s + m.total_fact_hours, 0);
      return {
        key: `team:${k}`,
        isTeam: true,
        employee_id: `team:${k}`,
        employee_name: k === '__none__' ? 'Без команды' : k,
        team: k === '__none__' ? null : k,
        months: monthSums,
        total_available_hours,
        total_fact_hours,
        children: members,
      } as TeamRow;
    });
  };
  const tree = groupByTeam(visible);

  // ------------ Cell helpers ------------
  const pctColor = (plan: number, fact: number): string | undefined => {
    if (plan <= 0) return undefined;
    const pct = (fact / plan) * 100;
    if (pct > 110) return 'var(--ant-color-error, #ff4d4f)';
    if (pct >= 100) return 'var(--ant-color-success, #52c41a)';
    if (pct < 50)  return 'var(--ant-color-text-secondary, #999)';
    return undefined;
  };
  const pctText = (plan: number, fact: number): string => {
    if (plan <= 0) return '—';
    return `${Math.round((fact / plan) * 100)}%`;
  };

  // ------------ Columns (responsive to toggles) ------------
  const months = QUARTER_MONTHS[Number(quarter)] || [];
  const monthGroup = (m: number) => ({
    title: MONTH_NAMES[m],
    children: [
      { title: 'План', key: `m${m}_plan`, width: 80,
        render: (_: unknown, r: TreeRow) => {
          const mc = r.months?.find((x) => x.month === m);
          return mc ? formatHours(mc.available_hours) : '—';
        } },
      ...(showFact ? [{
        title: 'Факт', key: `m${m}_fact`, width: 80,
        render: (_: unknown, r: TreeRow) => {
          const mc = r.months?.find((x) => x.month === m);
          return mc ? formatHours(mc.fact_hours) : '—';
        },
      }] : []),
      ...(showPct ? [{
        title: '%', key: `m${m}_pct`, width: 60,
        render: (_: unknown, r: TreeRow) => {
          const mc = r.months?.find((x) => x.month === m);
          if (!mc) return '—';
          return (
            <span style={{ color: pctColor(mc.available_hours, mc.fact_hours) }}>
              {pctText(mc.available_hours, mc.fact_hours)}
            </span>
          );
        },
      }] : []),
    ],
  });

  const nameColumn = {
    title: 'Сотрудник', key: 'name', fixed: 'left' as const, width: 380,
    render: (_: unknown, r: TreeRow) => {
      if ('isTeam' in r) {
        return <span style={{ fontWeight: 600 }}>{r.employee_name} <Text type="secondary">· {r.children.length}</Text></span>;
      }
      const teams = teamsByEmpId.get(r.employee_id) ?? [];
      const primary = teams.find(t => t.is_primary)?.team;
      const value = teams.map(t => t.team);
      return (
        <Space>
          <span>{r.employee_name}</span>
          <Select
            mode="multiple"
            allowClear
            size="small"
            style={{ width: 260 }}
            placeholder="Команды"
            value={value}
            options={teamOptions}
            onChange={(next: string[]) => replaceTeams.mutate({
              employeeId: r.employee_id,
              teams: next,
              primary: next.includes(primary ?? '') ? primary : next[0],
            })}
            onDropdownVisibleChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
            loading={jiraTeams.isFetching}
            tagRender={(props) => {
              const isPrimary = props.value === primary;
              return (
                <Tag
                  color={isPrimary ? 'gold' : 'default'}
                  closable={props.closable}
                  onClose={props.onClose}
                  style={{ marginInlineEnd: 4, cursor: 'pointer' }}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                  }}
                  onClick={() => {
                    if (!isPrimary) {
                      setPrimary.mutate({
                        employeeId: r.employee_id,
                        team: String(props.value),
                      });
                    }
                  }}
                  title={isPrimary ? 'Основная команда' : 'Клик — сделать основной'}
                >
                  {isPrimary ? '★ ' : ''}{props.label ?? String(props.value)}
                </Tag>
              );
            }}
          />
        </Space>
      );
    },
  };

  const columns = [
    nameColumn,
    ...months.map(monthGroup),
    {
      title: 'Итого',
      children: [
        { title: 'План', dataIndex: 'total_available_hours', render: formatHours, width: 90 },
        ...(showFact ? [{ title: 'Факт', dataIndex: 'total_fact_hours', render: formatHours, width: 90 }] : []),
        ...(showPct ? [{
          title: '%', width: 70,
          render: (_: unknown, r: TreeRow) => (
            <span style={{ color: pctColor(r.total_available_hours, r.total_fact_hours) }}>
              {pctText(r.total_available_hours, r.total_fact_hours)}
            </span>
          ),
        }] : []),
      ],
    },
  ];

  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
  const exportHref = `${apiBase}/exports/capacity.xlsx?year=${year}&quarter=${quarter}`;

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Select mode="multiple" allowClear placeholder="Фильтр по команде"
          style={{ minWidth: 220 }}
          value={selectedTeams}
          onChange={(v) => { setSelectedTeams(v); persist('ui_capacity_team_filter_teams', v.join(',')); }}
          options={[...teamOptions, { value: '__none__', label: 'Без команды' }]}
          onDropdownVisibleChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
          loading={jiraTeams.isFetching}
          notFoundContent={jiraTeams.isError ? 'Настройте поля команды' : undefined}
          showSearch optionFilterProp="label"
        />
        <Select mode="multiple" allowClear placeholder="Фильтр по сотруднику"
          style={{ minWidth: 260 }}
          value={selectedEmpIds}
          onChange={(v) => { setSelectedEmpIds(v); persist('ui_capacity_team_filter', v.join(',')); }}
          options={(employees ?? []).filter(e => e.is_active)
            .map(e => ({ value: e.id, label: e.display_name }))}
          showSearch optionFilterProp="label"
        />
        <Space>
          <Switch checked={showFact} onChange={(v) => { setShowFact(v); persist('ui_capacity_show_fact', v ? '1' : '0'); }} />
          <Text>Факт</Text>
          <Switch checked={showPct} onChange={(v) => { setShowPct(v); persist('ui_capacity_show_pct', v ? '1' : '0'); }} />
          <Text>%</Text>
        </Space>
        <Popconfirm
          title="Определить команды по ворклогам для всех без команды?"
          okText="Определить" cancelText="Отмена"
          onConfirm={() => autoDetect.mutate(undefined, {
            onSuccess: (s) => notification.success({
              title: 'Команды обновлены',
              description: `Назначено: ${s.assigned}, пропущено: ${s.skipped}`,
            }),
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          })}
        >
          <Button loading={autoDetect.isPending}>Определить команды авто</Button>
        </Popconfirm>
        <Popconfirm
          title="Пересчитать состав по worklog'ам активных задач?"
          okText="Пересчитать" cancelText="Отмена"
          okButtonProps={{ danger: true }}
          onConfirm={() => recalc.mutate(undefined, {
            onSuccess: (s) => notification.success({ title: 'Состав обновлён',
              description: `Активировано: ${s.activated}, деактивировано: ${s.deactivated}` }),
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          })}
        >
          <Button loading={recalc.isPending}>Пересчитать состав</Button>
        </Popconfirm>
        <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>Добавить сотрудника</Button>
        <Button href={exportHref} target="_blank" rel="noreferrer">Экспорт в Excel</Button>
      </Space>
      <Table
        dataSource={tree}
        rowKey="key"
        loading={isLoading}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        columns={columns as any}
        pagination={false}
        size="small"
        scroll={{ x: 1400 }}
        expandable={{ expandedRowKeys: tree.map(r => r.key), childrenColumnName: 'children' }}
        rowClassName={(r: TreeRow) => 'isTeam' in r ? 'capacity-team-row' : ''}
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
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useAbsences();
  const { data: employees } = useEmployees();
  const add = useAddAbsence();
  const remove = useRemoveAbsence();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const employeeMap = new Map(employees?.map((e) => [e.id, e.display_name]));
  const activeEmployees = (employees ?? []).filter(e => e.is_active);

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <AbsenceHeatmap
        year={Number(year)}
        quarter={Number(quarter)}
        employees={activeEmployees.map(e => ({ id: e.id, display_name: e.display_name }))}
        absences={data ?? []}
      />
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
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useCapacityRules();
  const add = useAddCapacityRule();
  const remove = useRemoveCapacityRule();
  const copy = useCopyRules();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const next = () => {
    const q = Number(quarter);
    return q === 4 ? { y: Number(year) + 1, q: 1 } : { y: Number(year), q: q + 1 };
  };
  const { y: toYear, q: toQuarter } = next();

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>Добавить правило</Button>
        <Popconfirm
          title={`Скопировать правила из Q${quarter} ${year} в Q${toQuarter} ${toYear}?`}
          okText="Скопировать" cancelText="Отмена"
          onConfirm={() => copy.mutate(
            { from_year: Number(year), from_quarter: Number(quarter), to_year: toYear, to_quarter: toQuarter },
            {
              onSuccess: (s) => notification.success({
                title: 'Скопировано',
                description: `Создано правил: ${s.created}`,
              }),
              onError: (e: Error) => {
                const msg = e.message || 'Ошибка';
                if (msg.includes('conflicts')) {
                  notification.warning({ title: 'Конфликт', description: msg });
                } else {
                  notification.error({ title: 'Ошибка', description: msg });
                }
              },
            },
          )}
        >
          <Button loading={copy.isPending}>Скопировать в следующий квартал</Button>
        </Popconfirm>
      </Space>
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
