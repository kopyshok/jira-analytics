import { useCallback, useEffect, useMemo, useState } from 'react';
import { Tabs, Table, Button, Space, Popconfirm, App, InputNumber, Form, Modal, Switch, Input, Typography, Tag } from 'antd';
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
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel } from '../../utils/roles';
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

type RoleRow = { key: string; role: EmployeeRole | null; label: string };

function RoleRulesSubtab() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const y = Number(year); const q = Number(quarter);

  const { data: rolesData = [] } = useRoles();
  const roleRows: RoleRow[] = useMemo(
    () => [
      { key: '__all__', role: null, label: 'Все роли (fallback)' },
      ...rolesData.filter(r => r.is_active).map(r => ({ key: r.code, role: r.code, label: r.label })),
    ],
    [rolesData],
  );

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
    for (const row of roleRows) {
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
      render: (v: string, r: RoleRow) => (
        <span style={{ fontWeight: r.role === null ? 600 : 400 }}>
          {v}{r.role === null && <Tag color="default" style={{ marginLeft: 8 }}>fallback</Tag>}
        </span>
      ),
    },
    ...activeWts.map(w => ({
      title: w.label,
      key: `wt_${w.id}`,
      width: 140,
      render: (_: unknown, row: RoleRow) => {
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
      render: (_: unknown, row: RoleRow) => {
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
            Σ ≠ 100%: {invalidRoles.map(r => getRoleLabel(rolesData, r)).join(', ')}
          </Text>
        )}
      </Space>
      {activeWts.length === 0 ? (
        <Text type="secondary">Нет активных типов работ. Добавьте их во вкладке «Виды работ».</Text>
      ) : (
        <Table
          dataSource={roleRows}
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

  const { data: rolesData = [] } = useRoles();
  const employees = useEmployees({ isActive: true });
  const wts = useMandatoryWorkTypes({ isActive: true });
  const roleRules = useRoleCapacityRules(y, q);
  const overrides = useEmployeeCapacityOverrides({ year: y, quarter: q });
  const saveBatch = useSaveEmployeeRulesBatch(y, q);
  const { matchesTeam } = useCapacityFilter();

  const activeWts = useMemo(
    () => (wts.data ?? []).filter(w => w.is_active),
    [wts.data],
  );

  const visibleEmployees = useMemo(
    () => (employees.data ?? []).filter(e => matchesTeam(e.id)),
    [employees.data, matchesTeam],
  );

  // Build baseline map (role rules resolved for each emp × wt).
  const baselineFor = useCallback(
    (emp: EmployeeResponse, wtId: string): number => {
      const rs = roleRules.data ?? [];
      if (emp.role) {
        const exact = rs.find(r => r.role === emp.role && r.work_type_id === wtId);
        if (exact) return exact.percent_of_norm;
      }
      const fallback = rs.find(r => r.role === null && r.work_type_id === wtId);
      return fallback?.percent_of_norm ?? 0;
    },
    [roleRules.data],
  );

  // Draft state: Map<employee_id, { enabled: boolean, pct: Map<wtId, number> }>.
  interface RowDraft { enabled: boolean; pct: Map<string, number> }
  const [draft, setDraft] = useState<Map<string, RowDraft>>(new Map());
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated && !overrides.isFetching) return;
    if (!overrides.data) return;
    const m = new Map<string, RowDraft>();
    for (const o of overrides.data) {
      const row = m.get(o.employee_id) ?? { enabled: true, pct: new Map() };
      row.pct.set(o.work_type_id, o.percent_of_norm);
      row.enabled = true;
      m.set(o.employee_id, row);
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(m);
    setHydrated(true);
  }, [overrides.data, hydrated, overrides.isFetching]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHydrated(false);
  }, [y, q]);

  const toggleOverride = (emp: EmployeeResponse, next: boolean) => {
    setDraft(prev => {
      const m = new Map(prev);
      const row = m.get(emp.id);
      if (next) {
        // Enable: if no row, seed from role baseline.
        if (row?.enabled) return m;
        const pct = new Map<string, number>();
        for (const w of activeWts) {
          pct.set(w.id, baselineFor(emp, w.id));
        }
        m.set(emp.id, { enabled: true, pct });
      } else if (row) {
        m.set(emp.id, { ...row, enabled: false });
      } else {
        m.set(emp.id, { enabled: false, pct: new Map() });
      }
      return m;
    });
  };

  const writeCell = (empId: string, wtId: string, next: number | null) => {
    setDraft(prev => {
      const m = new Map(prev);
      const row = m.get(empId) ?? { enabled: true, pct: new Map() };
      const pct = new Map(row.pct);
      if (next == null || Number.isNaN(next)) {
        pct.delete(wtId);
      } else {
        pct.set(wtId, next);
      }
      m.set(empId, { enabled: row.enabled, pct });
      return m;
    });
  };

  const sumFor = (empId: string): number => {
    const row = draft.get(empId);
    if (!row) return 0;
    let s = 0;
    for (const v of row.pct.values()) s += v;
    return s;
  };

  const isDirty = useMemo(() => {
    const orig = new Map<string, { enabled: boolean; pct: Map<string, number> }>();
    for (const o of overrides.data ?? []) {
      const row = orig.get(o.employee_id) ?? { enabled: true, pct: new Map() };
      row.pct.set(o.work_type_id, o.percent_of_norm);
      orig.set(o.employee_id, row);
    }
    for (const [empId, d] of draft) {
      const o = orig.get(empId);
      if (!d.enabled) {
        if (o) return true;
        continue;
      }
      if (!o) return true;
      if (o.pct.size !== d.pct.size) return true;
      for (const [k, v] of d.pct) {
        if (o.pct.get(k) !== v) return true;
      }
    }
    return false;
  }, [draft, overrides.data]);

  const invalidEmps: string[] = useMemo(() => {
    const out: string[] = [];
    for (const [empId, row] of draft) {
      if (!row.enabled) continue;
      const s = sumFor(empId);
      if (row.pct.size > 0 && Math.abs(s - 100) > 0.01) out.push(empId);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const handleSave = () => {
    const touchedIds = new Set<string>();
    for (const [empId, row] of draft) {
      touchedIds.add(empId);
      if (row.enabled && row.pct.size > 0 && Math.abs(sumFor(empId) - 100) > 0.01) {
        // UI already flagged; let server 422 for safety.
      }
    }
    const payload = Array.from(touchedIds).map(empId => {
      const row = draft.get(empId)!;
      if (!row.enabled) return { employee_id: empId, rules: [] };
      return {
        employee_id: empId,
        rules: Array.from(row.pct.entries())
          .filter(([, v]) => v > 0)
          .map(([wtId, v]) => ({ work_type_id: wtId, percent_of_norm: v })),
      };
    });
    saveBatch.mutate(payload, {
      onSuccess: () => notification.success({ title: 'Сохранено' }),
      onError: (e: unknown) => {
        const err = e as { message?: string; data?: { detail?: { errors?: EmployeeRulesValidationError[] } } };
        const errs = err.data?.detail?.errors;
        if (Array.isArray(errs) && errs.length) {
          const lines = errs
            .map(x => `${x.employee_id}: Σ = ${x.sum.toFixed(0)}% (ожидается 100%)`)
            .join('\n');
          notification.error({ title: 'Σ ≠ 100%', description: lines });
        } else {
          notification.error({ title: 'Ошибка', description: err.message ?? 'Неизвестная ошибка' });
        }
      },
    });
  };

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space>
        <Button
          type="primary"
          loading={saveBatch.isPending}
          disabled={!isDirty}
          onClick={handleSave}
        >
          Сохранить все {isDirty && <Tag style={{ marginLeft: 8 }}>есть изменения</Tag>}
        </Button>
        <Button disabled={!isDirty} onClick={() => setHydrated(false)}>Отменить</Button>
        <Text type="secondary">
          Переключатель «Override» клонирует правило роли в редактируемую копию. Σ = 100 % обязательно.
        </Text>
        {invalidEmps.length > 0 && (
          <Text type="danger">Σ ≠ 100%: {invalidEmps.length} сотрудник(ов)</Text>
        )}
      </Space>
      {visibleEmployees.map(emp => {
        const row = draft.get(emp.id) ?? { enabled: false, pct: new Map() };
        const s = sumFor(emp.id);
        const ok = Math.abs(s - 100) < 0.01;
        const baselineSum = activeWts.reduce((acc, w) => acc + baselineFor(emp, w.id), 0);
        return (
          <div key={emp.id} style={{
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 6, padding: 12,
          }}>
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Space>
                <Text strong>{emp.display_name}</Text>
                {emp.role && <Tag>{getRoleLabel(rolesData, emp.role)}</Tag>}
              </Space>
              <Space>
                <Text type="secondary">Override</Text>
                <Switch
                  checked={row.enabled}
                  onChange={(v) => toggleOverride(emp, v)}
                />
              </Space>
            </Space>
            {row.enabled ? (
              <Space wrap style={{ marginTop: 8 }}>
                {activeWts.map(w => (
                  <Space key={w.id} size={4}>
                    <Text type="secondary">{w.label}</Text>
                    <InputNumber
                      size="small"
                      min={0} max={100} step={1}
                      style={{ width: 90 }}
                      value={row.pct.get(w.id) ?? null}
                      addonAfter="%"
                      onChange={(v) => writeCell(emp.id, w.id, v == null ? null : Number(v))}
                    />
                  </Space>
                ))}
                <Text style={{ color: ok ? '#52c41a' : '#ff4d4f', marginLeft: 8 }}>
                  Σ = {s.toFixed(0)}%
                </Text>
              </Space>
            ) : (
              <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                Baseline роли: {activeWts.map(w =>
                  `${w.label} ${baselineFor(emp, w.id).toFixed(0)}%`).join(' · ')}
                {' · Σ '}{baselineSum.toFixed(0)}%
              </Text>
            )}
          </div>
        );
      })}
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
