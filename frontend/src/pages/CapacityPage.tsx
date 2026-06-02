import { useState, useEffect, useMemo, useCallback } from 'react';
import { Tabs, Table, Button, Space, App, Checkbox, DatePicker, Select, Form, Modal, AutoComplete, Typography, Switch, Tag, InputNumber } from 'antd';
import { PlusOutlined, TeamOutlined } from '@ant-design/icons';
import capacityHelp from '../../../docs/help/capacity.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import dayjs from 'dayjs';
import minMax from 'dayjs/plugin/minMax';
import PageHeader from '../components/shared/PageHeader';
import { useTeamCapacity, useEmployees, useSearchJiraUsers, useAddEmployeeFromJira, useReplaceEmployeeTeams, useSetPrimaryTeam, useUpdateEmployeeRole, useAutoDetectTeams } from '../hooks/useCapacity';
import { useJiraTeams } from '../hooks/useSync';
import { useAbsences, useAddAbsence, useAddAbsencesBatch, useRemoveAbsence } from '../hooks/useAbsences';
import { useAbsenceReasons } from '../hooks/useAbsenceReasons';
import AbsenceHeatmap from '../components/capacity/AbsenceHeatmap';
import RolesTab from '../components/capacity/RolesTab';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useGlobalPeriod } from '../hooks/useGlobalPeriod';
import { formatHours } from '../utils/format';
import { QUARTER_MONTHS, MONTH_NAMES } from '../utils/constants';
import { useRoles } from '../hooks/useRoles';
import type { QuarterCapacityResponse, AbsenceResponse, JiraUserSearchResult, EmployeeTeamItem, EmployeeRole } from '../types/api';

dayjs.extend(minMax);

const { Text } = Typography;

function TeamTab({ year, quarter }: { year: string; quarter: string }) {
  const { notification } = App.useApp();
  const { queryParams } = useGlobalTeamFilter();
  const { data, isLoading } = useTeamCapacity(year, quarter, queryParams.teams);
  const { data: employees } = useEmployees();
  const replaceTeams = useReplaceEmployeeTeams();
  const setPrimary = useSetPrimaryTeam();
  const updateRole = useUpdateEmployeeRole();
  const jiraTeams = useJiraTeams();
  const employeesFull = useEmployees({ withTeams: true });
  const teamsByEmpId = useMemo(() => {
    const m = new Map<string, EmployeeTeamItem[]>();
    (employeesFull.data ?? []).forEach(e => m.set(e.id, e.teams ?? []));
    return m;
  }, [employeesFull.data]);
  const roleByEmpId = useMemo(() => {
    const m = new Map<string, EmployeeRole | null>();
    (employeesFull.data ?? []).forEach(e => m.set(e.id, e.role ?? null));
    return m;
  }, [employeesFull.data]);

  const { data: roles = [] } = useRoles();
  const roleOptions = roles.filter(r => r.is_active).map(r => ({ value: r.code, label: r.label }));

  const teamOptions = (jiraTeams.data ?? []).map(t => ({ value: t, label: t }));

  const storedEmp = useGenericSetting('ui_capacity_team_filter');
  const storedShowFact = useGenericSetting('ui_capacity_show_fact');
  const storedShowPct  = useGenericSetting('ui_capacity_show_pct');
  const saveStored = useSaveGenericSetting();
  const [selectedEmpIds, setSelectedEmpIds] = useState<string[]>([]);
  const [showFact, setShowFact] = useState(false);
  const [showPct,  setShowPct]  = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const [addOpen, setAddOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(t);
  }, [query]);
  const searchRes = useSearchJiraUsers(debouncedQuery);
  const addMut = useAddEmployeeFromJira();
  const autoDetect = useAutoDetectTeams();
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
    if (storedEmp.data === undefined
        || storedShowFact.data === undefined || storedShowPct.data === undefined) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedEmpIds((storedEmp.data?.value || '').split(',').filter(Boolean));
    setShowFact(storedShowFact.data?.value === '1');
    setShowPct(storedShowPct.data?.value === '1');
    setHydrated(true);
  }, [hydrated, storedEmp.data, storedShowFact.data, storedShowPct.data]);

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
    const seenPerBucket = new Map<string, Set<string>>();
    for (const r of rows) {
      const k = r.team ?? '__none__';
      const seen = seenPerBucket.get(k) ?? new Set<string>();
      if (seen.has(r.employee_id)) continue;
      seen.add(r.employee_id);
      seenPerBucket.set(k, seen);
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
  const expandedRowKeys = useMemo(
    () => tree.filter(r => !collapsed.has(r.key)).map(r => r.key),
    [tree, collapsed],
  );

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
    title: 'Сотрудник', key: 'name', fixed: 'left' as const, width: 560,
    render: (_: unknown, r: TreeRow) => {
      if ('isTeam' in r) {
        return <span style={{ fontWeight: 600 }}>{r.employee_name} <Text type="secondary">· {r.children.length}</Text></span>;
      }
      const teams = teamsByEmpId.get(r.employee_id) ?? [];
      const primary = teams.find(t => t.is_primary)?.team;
      const value = teams.map(t => t.team);
      const role = roleByEmpId.get(r.employee_id) ?? null;
      return (
        <Space>
          <span>{r.employee_name}</span>
          <Select
            allowClear
            size="small"
            style={{ width: 150 }}
            placeholder="Роль"
            value={role}
            options={roleOptions}
            onChange={(next: EmployeeRole | null) =>
              updateRole.mutate({ employeeId: r.employee_id, role: next ?? null })
            }
          />
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
            onOpenChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
            loading={jiraTeams.isFetching}
            tagRender={(props) => {
              const isPrimary = props.value === primary;
              const label = String(props.label ?? props.value);
              return (
                <Tag
                  color={isPrimary ? 'gold' : 'default'}
                  closable={props.closable}
                  onClose={props.onClose}
                  style={{
                    marginInlineEnd: 4,
                    cursor: 'pointer',
                    maxWidth: 220,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    display: 'inline-flex',
                    alignItems: 'center',
                  }}
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
                  title={`${label}${isPrimary ? ' · основная' : ' · клик — сделать основной'}`}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {isPrimary ? '★ ' : ''}{label}
                  </span>
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

  const apiBase = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  const exportHref = `${apiBase}/exports/capacity.xlsx?year=${year}&quarter=${quarter}`;

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space wrap>
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
        <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>Добавить сотрудника</Button>
        <Button
          icon={<TeamOutlined />}
          loading={autoDetect.isPending}
          onClick={() =>
            autoDetect.mutate(undefined, {
              onSuccess: (res) =>
                notification.success({
                  title: 'Команды определены',
                  description: `Назначено: ${res.assigned}, пропущено: ${res.skipped}`,
                }),
              onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
            })
          }
        >
          Авто-определить команды
        </Button>
        <Button onClick={() => setCollapsed(new Set(tree.map(r => r.key)))}>Свернуть все</Button>
        <Button onClick={() => setCollapsed(new Set())}>Развернуть все</Button>
        <Button href={exportHref} target="_blank" rel="noreferrer">Экспорт в Excel</Button>
      </Space>
      <Table
        dataSource={tree}
        rowKey={(r: TreeRow) => 'isTeam' in r ? r.key : `${r.team ?? '__none__'}::${r.employee_id}`}
        loading={isLoading}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        columns={columns as any}
        pagination={false}
        size="small"
        scroll={{ x: 1400 }}
        expandable={{
          expandedRowKeys,
          childrenColumnName: 'children',
          onExpand: (expand, record) => {
            const r = record as TreeRow;
            if (!('isTeam' in r)) return;
            setCollapsed(prev => {
              const next = new Set(prev);
              if (expand) next.delete(r.key); else next.add(r.key);
              return next;
            });
          },
        }}
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

function AbsencesTab({ year, quarter }: { year: string; quarter: string }) {
  const { notification } = App.useApp();
  const { data: absences, isLoading } = useAbsences();
  const { data: employees } = useEmployees();
  const { data: reasons } = useAbsenceReasons();
  const add = useAddAbsence();
  const batchAdd = useAddAbsencesBatch();
  const remove = useRemoveAbsence();
  const { queryParams } = useGlobalTeamFilter();
  const empsWithTeams = useEmployees({ withTeams: true });
  const [singleOpen, setSingleOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [editEmployeeId, setEditEmployeeId] = useState<string | null>(null);
  const [singleForm] = Form.useForm();
  const [bulkForm] = Form.useForm();
  const [showUnplannedOnly, setShowUnplannedOnly] = useState(false);

  const selectedTeams = useMemo(
    () => (queryParams.teams ? queryParams.teams.split(',').filter(Boolean) : []),
    [queryParams.teams],
  );
  const employeeTeamMap = useMemo(() => {
    const m = new Map<string, string[]>();
    (empsWithTeams.data ?? []).forEach(e => {
      m.set(e.id, (e.teams ?? []).map(t => t.team));
    });
    return m;
  }, [empsWithTeams.data]);
  const matchesTeam = useCallback((employeeId: string): boolean => {
    if (selectedTeams.length === 0) return true;
    const teams = employeeTeamMap.get(employeeId) ?? [];
    return teams.some(t => selectedTeams.includes(t));
  }, [selectedTeams, employeeTeamMap]);

  const activeEmployees = (employees ?? []).filter(e => e.is_active && matchesTeam(e.id));
  const activeReasons = (reasons ?? []).filter(r => r.is_active);

  // Quarter bounds.
  const months = QUARTER_MONTHS[Number(quarter)] ?? [];
  const periodStart = dayjs(`${year}-${String(months[0] ?? 1).padStart(2, '0')}-01`);
  const periodEnd = periodStart.add(3, 'month').subtract(1, 'day');

  const absencesByEmp = useMemo(() => {
    const m = new Map<string, AbsenceResponse[]>();
    (absences ?? []).filter(a => matchesTeam(a.employee_id)).forEach(a => {
      if (showUnplannedOnly && a.reason_is_planned) return;
      // Keep only absences overlapping period.
      const s = dayjs(a.start_date); const e = dayjs(a.end_date);
      if (e.isBefore(periodStart) || s.isAfter(periodEnd)) return;
      const arr = m.get(a.employee_id) ?? [];
      arr.push(a);
      m.set(a.employee_id, arr);
    });
    return m;
  }, [absences, matchesTeam, showUnplannedOnly, periodStart, periodEnd]);

  const openAddForEmp = (empId: string) => {
    setEditEmployeeId(empId);
    singleForm.resetFields();
    singleForm.setFieldsValue({
      employee_id: empId,
      reason_id: activeReasons[0]?.id,
    });
    setSingleOpen(true);
  };

  const rows = activeEmployees.map(e => ({
    employee_id: e.id,
    display_name: e.display_name,
    absences: absencesByEmp.get(e.id) ?? [],
  }));

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <AbsenceHeatmap
        year={Number(year)}
        quarter={Number(quarter)}
        employees={activeEmployees.map(e => ({ id: e.id, display_name: e.display_name }))}
        absences={(absences ?? []).filter(r => matchesTeam(r.employee_id))}
      />
      <Space wrap>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => {
          bulkForm.resetFields();
          bulkForm.setFieldsValue({ reason_id: activeReasons[0]?.id });
          setBulkOpen(true);
        }}>
          Массовое добавление
        </Button>
        <Space>
          <Switch checked={showUnplannedOnly} onChange={setShowUnplannedOnly} />
          <Text>Только внеплановые</Text>
        </Space>
      </Space>

      <Table
        dataSource={rows}
        rowKey="employee_id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Сотрудник', dataIndex: 'display_name', width: 240, fixed: 'left' as const },
          {
            title: `Отсутствия в Q${quarter} ${year}`,
            render: (_: unknown, r: typeof rows[number]) => (
              <Space wrap>
                {r.absences.map(a => (
                  <Tag
                    key={a.id}
                    color={a.reason_color ?? 'default'}
                    closable
                    onClose={(ev) => {
                      ev.preventDefault();
                      remove.mutate(a.id);
                    }}
                    style={{ cursor: 'default' }}
                  >
                    {a.reason_label}: {dayjs(a.start_date).format('DD.MM')}—
                    {dayjs(a.end_date).format('DD.MM')}
                  </Tag>
                ))}
                <Button size="small" icon={<PlusOutlined />} onClick={() => openAddForEmp(r.employee_id)}>
                  добавить
                </Button>
              </Space>
            ),
          },
          {
            title: 'Дней', width: 80, align: 'right' as const,
            render: (_: unknown, r: typeof rows[number]) => {
              let days = 0;
              for (const a of r.absences) {
                const s = dayjs.max(dayjs(a.start_date), periodStart);
                const e = dayjs.min(dayjs(a.end_date), periodEnd);
                if (e && s) days += e.diff(s, 'day') + 1;
              }
              return days;
            },
          },
        ]}
      />

      {/* Single-entry modal */}
      <Modal
        title="Новое отсутствие"
        open={singleOpen}
        onCancel={() => setSingleOpen(false)}
        onOk={() => singleForm.submit()}
        confirmLoading={add.isPending}
      >
        <Form form={singleForm} layout="vertical" onFinish={(v) => {
          add.mutate({
            employee_id: v.employee_id,
            start_date: v.dates[0].format('YYYY-MM-DD'),
            end_date: v.dates[1].format('YYYY-MM-DD'),
            reason_id: v.reason_id,
          }, {
            onSuccess: () => {
              setSingleOpen(false);
              notification.success({ title: 'Отсутствие добавлено' });
            },
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          });
        }}>
          <Form.Item name="employee_id" label="Сотрудник" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label"
              options={(employees ?? []).map(e => ({ value: e.id, label: e.display_name }))}
              disabled={!!editEmployeeId}
            />
          </Form.Item>
          <Form.Item name="reason_id" label="Причина" rules={[{ required: true }]}>
            <Select options={activeReasons.map(r => ({
              value: r.id, label: r.label,
            }))} />
          </Form.Item>
          <Form.Item name="dates" label="Даты" rules={[{ required: true }]}>
            <DatePicker.RangePicker format="DD.MM.YYYY" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Bulk-entry modal */}
      <Modal
        title="Массовое добавление отсутствий"
        open={bulkOpen}
        onCancel={() => setBulkOpen(false)}
        onOk={() => bulkForm.submit()}
        confirmLoading={batchAdd.isPending}
        width={640}
      >
        <Form form={bulkForm} layout="vertical" onFinish={(v) => {
          batchAdd.mutate({
            employee_ids: v.employee_ids,
            start_date: v.dates[0].format('YYYY-MM-DD'),
            end_date: v.dates[1].format('YYYY-MM-DD'),
            reason_id: v.reason_id,
          }, {
            onSuccess: (rows) => {
              setBulkOpen(false);
              notification.success({ title: 'Создано записей', description: String(rows.length) });
            },
            onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
          });
        }}>
          <Form.Item name="employee_ids" label="Сотрудники" rules={[{ required: true }]}>
            <Select mode="multiple" showSearch optionFilterProp="label"
              options={activeEmployees.map(e => ({ value: e.id, label: e.display_name }))} />
          </Form.Item>
          <Form.Item name="reason_id" label="Причина" rules={[{ required: true }]}>
            <Select options={activeReasons.map(r => ({ value: r.id, label: r.label }))} />
          </Form.Item>
          <Form.Item name="dates" label="Диапазон" rules={[{ required: true }]}>
            <DatePicker.RangePicker format="DD.MM.YYYY" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}


function CapacityPeriodSelector({
  year, quarter, overrideOn, onToggleOverride, onYearChange, onQuarterChange,
}: {
  year: string;
  quarter: string;
  overrideOn: boolean;
  onToggleOverride: (v: boolean) => void;
  onYearChange: (y: string) => void;
  onQuarterChange: (q: string) => void;
}) {
  return (
    <Space>
      <Checkbox checked={overrideOn} onChange={e => onToggleOverride(e.target.checked)}>
        Уточнить период
      </Checkbox>
      {overrideOn && (
        <>
          <span>Год:</span>
          <InputNumber
            value={Number(year)}
            min={2020}
            max={2030}
            onChange={v => v && onYearChange(String(v))}
            style={{ width: 100 }}
          />
          <span>Квартал:</span>
          <Select
            value={quarter}
            onChange={onQuarterChange}
            style={{ width: 80 }}
            options={[
              { value: '1', label: 'Q1' },
              { value: '2', label: 'Q2' },
              { value: '3', label: 'Q3' },
              { value: '4', label: 'Q4' },
            ]}
          />
        </>
      )}
    </Space>
  );
}

export default function CapacityPage() {
  const { period: globalPeriod } = useGlobalPeriod();
  const [overrideOn, setOverrideOn] = useState(false);
  const [localYear, setLocalYear] = useState<string>(String(globalPeriod.year));
  const [localQuarter, setLocalQuarter] = useState<string>(String(globalPeriod.quarter));
  useRegisterHelp('Capacity сотрудников', capacityHelp);

  const year = overrideOn ? localYear : String(globalPeriod.year);
  const quarter = overrideOn ? localQuarter : String(globalPeriod.quarter);

  const handleToggleOverride = (v: boolean) => {
    if (v) {
      setLocalYear(String(globalPeriod.year));
      setLocalQuarter(String(globalPeriod.quarter));
    }
    setOverrideOn(v);
  };

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader
        eyebrow="Планирование"
        title="Ресурсы команды"
        subtitle="План · факт · отпуска · правила обязательной загрузки"
        actions={
          <CapacityPeriodSelector
            year={year}
            quarter={quarter}
            overrideOn={overrideOn}
            onToggleOverride={handleToggleOverride}
            onYearChange={setLocalYear}
            onQuarterChange={setLocalQuarter}
          />
        }
      />
      <Tabs items={[
        { key: 'team', label: 'Команда', children: <TeamTab year={year} quarter={quarter} /> },
        { key: 'absences', label: 'Отсутствия', children: <AbsencesTab year={year} quarter={quarter} /> },
        { key: 'roles', label: 'Роли', children: <RolesTab /> },
      ]} />
    </Space>
  );
}
