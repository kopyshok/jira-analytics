import { useCallback, useEffect, useMemo, useState } from 'react';
import { Tabs, Table, Button, Space, Popconfirm, App, InputNumber, Select, Form, Modal, Switch, Input, Typography, Tag } from 'antd';
import { PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import {
  useMandatoryWorkTypes,
  useCreateMandatoryWorkType,
  useUpdateMandatoryWorkType,
  useDeleteMandatoryWorkType,
  useReorderMandatoryWorkTypes,
  useRoleCapacityRules,
  useSaveRoleRulesBatch,
  useCopyRoleCapacityRulesToQuarter,
  useEmployeeCapacityOverrides,
  useSaveEmployeeRulesBatch,
  useEmployees,
} from '../../hooks/useCapacity';
import { useQuarterYear } from '../../hooks/useQuarterYear';
import { useCapacityFilter } from '../../hooks/useCapacityFilter';
import { EMPLOYEE_ROLES, EMPLOYEE_ROLE_LABELS } from '../../utils/constants';
import type {
  EmployeeRole,
  MandatoryWorkType,
  RoleRuleIn,
  RoleRulesValidationError,
  EmployeeRulesValidationError,
  EmployeeResponse,
} from '../../types/api';

const { Text } = Typography;

// ══════════════════════════════════════════════════════════════
// Subtab 1: Mandatory work type directory
// ══════════════════════════════════════════════════════════════

function WorkTypesSubtab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useMandatoryWorkTypes();
  const create = useCreateMandatoryWorkType();
  const update = useUpdateMandatoryWorkType();
  const remove = useDeleteMandatoryWorkType();
  const reorder = useReorderMandatoryWorkTypes();

  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const items = data ?? [];

  const swap = (idx: number, dir: -1 | 1) => {
    const newOrder = [...items];
    const j = idx + dir;
    if (j < 0 || j >= newOrder.length) return;
    [newOrder[idx], newOrder[j]] = [newOrder[j], newOrder[idx]];
    reorder.mutate(newOrder.map(x => x.id));
  };

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>
          Добавить тип работ
        </Button>
        <Text type="secondary">Справочник видов работ, покрывающих 100 % времени сотрудника.</Text>
      </Space>
      <Modal
        title="Новый тип обязательных работ"
        open={open}
        onCancel={() => { setOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => {
          create.mutate(
            { code: v.code, label: v.label, is_active: true, sort_order: items.length },
            {
              onSuccess: () => {
                setOpen(false); form.resetFields();
                notification.success({ title: 'Тип работ добавлен' });
              },
              onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
            },
          );
        }}>
          <Form.Item name="code" label="Code (slug)" rules={[{ required: true }]}>
            <Input placeholder="например, organizational" />
          </Form.Item>
          <Form.Item name="label" label="Название" rules={[{ required: true }]}>
            <Input placeholder="например, Организационные вопросы" />
          </Form.Item>
        </Form>
      </Modal>
      <Table<MandatoryWorkType>
        dataSource={items}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          {
            title: '↕', width: 80,
            render: (_: unknown, _r: MandatoryWorkType, idx: number) => (
              <Space size={4}>
                <Button size="small" icon={<ArrowUpOutlined />} disabled={idx === 0}
                  onClick={() => swap(idx, -1)} />
                <Button size="small" icon={<ArrowDownOutlined />} disabled={idx === items.length - 1}
                  onClick={() => swap(idx, 1)} />
              </Space>
            ),
          },
          { title: 'Code', dataIndex: 'code', width: 200 },
          { title: 'Название', dataIndex: 'label' },
          {
            title: 'Активен', dataIndex: 'is_active', width: 100,
            render: (v: boolean, r) => (
              <Switch checked={v} onChange={(next) => update.mutate(
                { id: r.id, body: { is_active: next } },
                { onError: (e) => notification.error({ title: 'Ошибка', description: e.message }) },
              )} />
            ),
          },
          {
            title: '', width: 50,
            render: (_, r) => (
              <Popconfirm
                title="Удалить?"
                description="Если тип привязан к правилам — деактивируйте его вместо удаления."
                onConfirm={() => remove.mutate(r.id, {
                  onSuccess: () => notification.success({ title: 'Удалено' }),
                  onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
                })}
              >
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}

// ══════════════════════════════════════════════════════════════
// Subtab 2: Role × work_type matrix
// ══════════════════════════════════════════════════════════════

const ROLE_ROWS: Array<{ key: string; role: EmployeeRole | null; label: string }> = [
  { key: '__all__', role: null, label: 'Все роли (fallback)' },
  ...EMPLOYEE_ROLES.map(r => ({ key: r, role: r, label: EMPLOYEE_ROLE_LABELS[r] })),
];

function RoleRulesSubtab() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const y = Number(year); const q = Number(quarter);

  const wts = useMandatoryWorkTypes({ isActive: true });
  const rules = useRoleCapacityRules(y, q);
  const saveBatch = useSaveRoleRulesBatch(y, q);
  const copy = useCopyRoleCapacityRulesToQuarter();

  const activeWts = useMemo(
    () => (wts.data ?? []).filter(w => w.is_active),
    [wts.data],
  );

  // Draft state: Map<"role|work_type_id", number | null>.
  const keyOf = (role: EmployeeRole | null, wtId: string) =>
    `${role ?? '__all__'}::${wtId}`;

  const [draft, setDraft] = useState<Map<string, number | null>>(new Map());
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated && !rules.isFetching) return;
    if (!rules.data) return;
    const m = new Map<string, number | null>();
    for (const r of rules.data) {
      m.set(keyOf(r.role as EmployeeRole | null, r.work_type_id), r.percent_of_norm);
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(m);
    setHydrated(true);
  }, [rules.data, hydrated, rules.isFetching]);

  // Re-hydrate on year/quarter change.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHydrated(false);
  }, [y, q]);

  const readCell = (role: EmployeeRole | null, wtId: string): number | null => {
    const v = draft.get(keyOf(role, wtId));
    return v ?? null;
  };

  const writeCell = (role: EmployeeRole | null, wtId: string, next: number | null) => {
    setDraft(prev => {
      const m = new Map(prev);
      if (next == null || Number.isNaN(next)) {
        m.delete(keyOf(role, wtId));
      } else {
        m.set(keyOf(role, wtId), next);
      }
      return m;
    });
  };

  const sumByRole = (role: EmployeeRole | null): number => {
    return activeWts.reduce((acc, w) => {
      const v = readCell(role, w.id);
      return acc + (v ?? 0);
    }, 0);
  };

  const isDirty = useMemo(() => {
    const original = new Map<string, number>();
    (rules.data ?? []).forEach(r =>
      original.set(keyOf(r.role as EmployeeRole | null, r.work_type_id), r.percent_of_norm),
    );
    if (original.size !== draft.size) return true;
    for (const [k, v] of draft) {
      if (original.get(k) !== v) return true;
    }
    return false;
  }, [draft, rules.data]);

  const invalidRoles: EmployeeRole[] = useMemo(() => {
    const bad: EmployeeRole[] = [];
    for (const row of ROLE_ROWS) {
      const s = sumByRole(row.role);
      if (s > 0 && Math.abs(s - 100) > 0.01) {
        if (row.role !== null) bad.push(row.role);
      }
    }
    return bad;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, activeWts]);

  const handleSave = () => {
    const rulesOut: RoleRuleIn[] = [];
    for (const [key, value] of draft) {
      if (value == null || value === 0) continue;
      const [roleKey, wtId] = key.split('::');
      rulesOut.push({
        role: roleKey === '__all__' ? null : (roleKey as EmployeeRole),
        work_type_id: wtId,
        percent_of_norm: value,
      });
    }
    saveBatch.mutate(rulesOut, {
      onSuccess: () => notification.success({ title: 'Сохранено' }),
      onError: (e: unknown) => {
        const err = e as { message?: string; data?: { detail?: { errors?: RoleRulesValidationError[] } } };
        const errs = err.data?.detail?.errors;
        if (Array.isArray(errs) && errs.length) {
          const lines = errs.map(x =>
            `${x.role ?? 'Все роли'}: Σ = ${x.sum.toFixed(0)}% (ожидается 100%)`,
          ).join('\n');
          notification.error({ title: 'Σ ≠ 100%', description: lines });
        } else {
          notification.error({ title: 'Ошибка', description: err.message ?? 'Неизвестная ошибка' });
        }
      },
    });
  };

  const handleReset = () => {
    setHydrated(false);
  };

  const next = q === 4 ? { y: y + 1, q: 1 } : { y, q: q + 1 };

  const columns = [
    {
      title: 'Роль / тип работ', dataIndex: 'label', width: 240,
      fixed: 'left' as const,
      render: (v: string, r: typeof ROLE_ROWS[number]) => (
        <span style={{ fontWeight: r.role === null ? 600 : 400 }}>
          {v}{r.role === null && <Tag color="default" style={{ marginLeft: 8 }}>fallback</Tag>}
        </span>
      ),
    },
    ...activeWts.map(w => ({
      title: w.label,
      key: `wt_${w.id}`,
      width: 140,
      render: (_: unknown, row: typeof ROLE_ROWS[number]) => {
        const v = readCell(row.role, w.id);
        return (
          <InputNumber
            size="small"
            min={0} max={100} step={1}
            style={{ width: '100%' }}
            value={v}
            placeholder="—"
            addonAfter="%"
            onChange={(nv) =>
              writeCell(row.role, w.id, nv == null ? null : Number(nv))
            }
          />
        );
      },
    })),
    {
      title: 'Σ', key: 'sum', width: 80, fixed: 'right' as const,
      render: (_: unknown, row: typeof ROLE_ROWS[number]) => {
        const s = sumByRole(row.role);
        const ok = Math.abs(s - 100) < 0.01;
        const empty = s === 0;
        const color = empty ? undefined : ok ? '#52c41a' : '#ff4d4f';
        return <Text style={{ color }}>{s.toFixed(0)}%</Text>;
      },
    },
  ];

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space>
        <Text>
          Правила для <b>Q{q} {y}</b>. В каждой строке сумма долей должна быть равна <b>100 %</b>
          (пустая строка допустима). «Все роли» — fallback для сотрудников без явного правила.
        </Text>
      </Space>
      <Space>
        <Button
          type="primary"
          loading={saveBatch.isPending}
          disabled={!isDirty}
          onClick={handleSave}
        >
          Сохранить {isDirty && <Tag style={{ marginLeft: 8 }}>есть изменения</Tag>}
        </Button>
        <Button disabled={!isDirty} onClick={handleReset}>Отменить</Button>
        <Popconfirm
          title={`Скопировать все правила из Q${q} ${y} в Q${next.q} ${next.y}?`}
          okText="Скопировать" cancelText="Отмена"
          onConfirm={() => copy.mutate(
            { from_year: y, from_quarter: q, to_year: next.y, to_quarter: next.q },
            {
              onSuccess: (s) => notification.success({
                title: 'Скопировано', description: `Создано правил: ${s.created}`,
              }),
              onError: (e) => {
                const msg = e.message || 'Ошибка';
                if (msg.includes('conflicts')) {
                  notification.warning({ title: 'Конфликт', description: 'В целевом квартале уже есть правила.' });
                } else {
                  notification.error({ title: 'Ошибка', description: msg });
                }
              },
            },
          )}
        >
          <Button loading={copy.isPending}>Скопировать в следующий квартал</Button>
        </Popconfirm>
        {invalidRoles.length > 0 && (
          <Text type="danger">
            Σ ≠ 100%: {invalidRoles.map(r => EMPLOYEE_ROLE_LABELS[r]).join(', ')}
          </Text>
        )}
      </Space>
      {activeWts.length === 0 ? (
        <Text type="secondary">Нет активных типов работ. Добавьте их во вкладке «Виды работ».</Text>
      ) : (
        <Table
          dataSource={ROLE_ROWS}
          rowKey="key"
          loading={rules.isLoading || wts.isLoading}
          pagination={false}
          size="small"
          scroll={{ x: 240 + activeWts.length * 140 + 80 }}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          columns={columns as any}
        />
      )}
    </Space>
  );
}

// ══════════════════════════════════════════════════════════════
// Subtab 3: Employee overrides
// ══════════════════════════════════════════════════════════════

function EmployeeOverridesSubtab() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const y = Number(year); const q = Number(quarter);

  const employees = useEmployees({ isActive: true });
  const wts = useMandatoryWorkTypes({ isActive: true });
  const roleRules = useRoleCapacityRules(y, q);
  const overrides = useEmployeeCapacityOverrides({ year: y, quarter: q });
  const create = useCreateEmployeeCapacityOverride();
  const update = useUpdateEmployeeCapacityOverride();
  const remove = useDeleteEmployeeCapacityOverride();
  const { matchesTeam } = useCapacityFilter();
  const visibleOverrides = (overrides.data ?? []).filter(o => matchesTeam(o.employee_id));

  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const empById = useMemo(() => {
    const m = new Map<string, EmployeeResponse>();
    (employees.data ?? []).forEach(e => m.set(e.id, e));
    return m;
  }, [employees.data]);

  const wtById = useMemo(() => {
    const m = new Map<string, string>();
    (wts.data ?? []).forEach(w => m.set(w.id, w.label));
    return m;
  }, [wts.data]);

  const basePercentFor = (emp: EmployeeResponse | undefined, wtId: string): number => {
    if (!emp) return 0;
    const rules = roleRules.data ?? [];
    const role = emp.role;
    const exact = role ? rules.find(r => r.role === role && r.work_type_id === wtId) : undefined;
    if (exact) return exact.percent_of_norm;
    const fallback = rules.find(r => r.role === null && r.work_type_id === wtId);
    return fallback?.percent_of_norm ?? 0;
  };

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space>
        <Button icon={<PlusOutlined />} type="primary" onClick={() => setOpen(true)}>
          Добавить индивидуальное правило
        </Button>
        <Text type="secondary">
          Правила ниже имеют приоритет над «По ролям» для указанного сотрудника и типа работ на Q{q} {y}.
        </Text>
      </Space>
      <Modal
        title="Новое индивидуальное правило"
        open={open}
        onCancel={() => { setOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => {
          create.mutate(
            { year: y, quarter: q, employee_id: v.employee_id, work_type_id: v.work_type_id, percent_of_norm: v.percent },
            {
              onSuccess: () => { setOpen(false); form.resetFields(); notification.success({ title: 'Правило добавлено' }); },
              onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
            },
          );
        }}>
          <Form.Item name="employee_id" label="Сотрудник" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label"
              options={(employees.data ?? []).map(e => ({ value: e.id, label: e.display_name }))} />
          </Form.Item>
          <Form.Item name="work_type_id" label="Тип обязательных работ" rules={[{ required: true }]}>
            <Select options={(wts.data ?? []).filter(w => w.is_active)
              .map(w => ({ value: w.id, label: w.label }))} />
          </Form.Item>
          <Form.Item name="percent" label="% от нормы" rules={[{ required: true }]} initialValue={10}>
            <InputNumber min={0} max={100} style={{ width: '100%' }} addonAfter="%" />
          </Form.Item>
        </Form>
      </Modal>
      <Table<EmployeeCapacityOverride>
        dataSource={visibleOverrides}
        rowKey="id"
        loading={overrides.isLoading}
        pagination={false}
        size="small"
        columns={[
          {
            title: 'Сотрудник', dataIndex: 'employee_id',
            render: (id: string) => empById.get(id)?.display_name ?? id,
          },
          {
            title: 'Роль', dataIndex: 'employee_id', width: 150,
            render: (id: string) => {
              const r = empById.get(id)?.role;
              return r ? <Tag>{EMPLOYEE_ROLE_LABELS[r]}</Tag> : <Text type="secondary">—</Text>;
            },
          },
          {
            title: 'Тип работ', dataIndex: 'work_type_id',
            render: (id: string) => wtById.get(id) ?? id,
          },
          {
            title: '% override', dataIndex: 'percent_of_norm', width: 140,
            render: (v: number, r) => (
              <InputNumber
                size="small" min={0} max={100}
                style={{ width: '100%' }}
                value={v}
                addonAfter="%"
                onBlur={(e) => {
                  const next = Number(e.currentTarget.value);
                  if (!Number.isFinite(next) || next === v) return;
                  update.mutate(
                    { id: r.id, percent: next, year: y, quarter: q },
                    { onError: (e) => notification.error({ title: 'Ошибка', description: e.message }) },
                  );
                }}
                onPressEnter={(e) => (e.currentTarget as HTMLInputElement).blur()}
              />
            ),
          },
          {
            title: '% базовое (роль)', width: 140,
            render: (_: unknown, r: EmployeeCapacityOverride) => {
              const base = basePercentFor(empById.get(r.employee_id), r.work_type_id);
              const diff = r.percent_of_norm - base;
              return (
                <Space size={4}>
                  <Text type="secondary">{base.toFixed(0)}%</Text>
                  {diff !== 0 && (
                    <Tag color={diff > 0 ? 'red' : 'blue'}>
                      {diff > 0 ? '+' : ''}{diff.toFixed(0)}
                    </Tag>
                  )}
                </Space>
              );
            },
          },
          {
            title: '', width: 50,
            render: (_: unknown, r: EmployeeCapacityOverride) => (
              <Popconfirm title="Удалить?" onConfirm={() => remove.mutate(
                { id: r.id, year: y, quarter: q },
                { onError: (e) => notification.error({ title: 'Ошибка', description: e.message }) },
              )}>
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}

// ══════════════════════════════════════════════════════════════
// Root
// ══════════════════════════════════════════════════════════════

export default function RulesTabV2() {
  return (
    <Tabs
      items={[
        { key: 'work_types', label: 'Виды работ', children: <WorkTypesSubtab /> },
        { key: 'by_role', label: 'Правила по ролям', children: <RoleRulesSubtab /> },
        { key: 'by_employee', label: 'Индивидуальные правила', children: <EmployeeOverridesSubtab /> },
      ]}
    />
  );
}
