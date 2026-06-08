import { useEffect, useMemo, useState } from 'react';
import {
  App, Button, InputNumber, Popover, Select, Space, Table, Tooltip,
} from 'antd';
import { CopyOutlined, DeleteOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons';
import { useScenarioRules, usePutScenarioRules, useCopyRulesFromScenario, useScenarios } from '../../hooks/usePlanning';
import { useRoles } from '../../hooks/useRoles';
import { useMandatoryWorkTypes } from '../../hooks/useCapacity';
import { uid } from '../../utils/uid';
import type { ScenarioRuleInput } from '../../types/api';

interface RuleDraft extends ScenarioRuleInput {
  _key: string;
}

// AntD 6 Select запрещает value: null в options. Используем sentinel для UI,
// конвертируем в null на границе ввода/вывода.
const ALL_ROLES_SENTINEL = '__all__';
const toRoleUi = (role: string | null): string => role ?? ALL_ROLES_SENTINEL;
const fromRoleUi = (v: string): string | null => v === ALL_ROLES_SENTINEL ? null : v;

interface Props {
  scenarioId: string;
}

export default function ScenarioRulesEditor({ scenarioId }: Props) {
  const { notification } = App.useApp();
  const { data: serverRules = [] } = useScenarioRules(scenarioId);
  const { data: roles = [] } = useRoles();
  const { data: workTypes = [] } = useMandatoryWorkTypes({ isActive: true });
  const put = usePutScenarioRules();
  const copy = useCopyRulesFromScenario();
  const { data: approvedScenarios = [] } = useScenarios(undefined, undefined, 'approved');
  const [copyOpen, setCopyOpen] = useState(false);
  const [copySourceId, setCopySourceId] = useState<string | undefined>(undefined);

  const [drafts, setDrafts] = useState<RuleDraft[]>([]);
  const [dirty, setDirty] = useState(false);

  // Инициализируем черновик при первой загрузке правил с сервера
  useEffect(() => {
    if (!dirty) {
      setDrafts(
        serverRules.map((r) => ({
          _key: r.id,
          role: r.role,
          work_type_id: r.work_type_id,
          percent_of_norm: r.percent_of_norm,
        })),
      );
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverRules]);

  // Дубликаты: пары (role, work_type_id) не уникальны
  const duplicateKeys = useMemo(() => {
    const seen = new Set<string>();
    const dups = new Set<string>();
    for (const d of drafts) {
      const key = `${d.role ?? '__all__'}::${d.work_type_id}`;
      if (seen.has(key)) dups.add(key);
      else seen.add(key);
    }
    return dups;
  }, [drafts]);

  const hasDuplicates = duplicateKeys.size > 0;

  const roleOptions = useMemo(() => [
    { value: ALL_ROLES_SENTINEL, label: 'Все' },
    ...roles.map((r) => ({ value: r.code, label: r.label })),
  ], [roles]);

  const workTypeOptions = useMemo(() =>
    workTypes.map((wt) => ({ value: wt.id, label: wt.label })),
  [workTypes]);

  const updateRow = (key: string, patch: Partial<RuleDraft>) => {
    setDrafts((prev) => prev.map((d) => d._key === key ? { ...d, ...patch } : d));
    setDirty(true);
  };

  const addRow = () => {
    setDrafts((prev) => [
      ...prev,
      {
        _key: uid(),
        role: null,
        work_type_id: workTypes[0]?.id ?? '',
        percent_of_norm: 0,
      },
    ]);
    setDirty(true);
  };

  const removeRow = (key: string) => {
    setDrafts((prev) => prev.filter((d) => d._key !== key));
    setDirty(true);
  };

  const handleReset = () => {
    setDrafts(
      serverRules.map((r) => ({
        _key: r.id,
        role: r.role,
        work_type_id: r.work_type_id,
        percent_of_norm: r.percent_of_norm,
      })),
    );
    setDirty(false);
  };

  const handleSave = () => {
    // Предупреждение если сумма % по роли > 100
    const byRole = new Map<string, number>();
    for (const d of drafts) {
      const k = d.role ?? '__all__';
      byRole.set(k, (byRole.get(k) ?? 0) + d.percent_of_norm);
    }
    for (const [role, sum] of byRole) {
      if (sum > 100) {
        const roleLabel = role === '__all__' ? 'Все' : (roles.find((r) => r.code === role)?.label ?? role);
        notification.warning({
          title: `Сумма % по роли «${roleLabel}» = ${sum}`,
          description: 'Сохраняем как есть. Проверьте правила.',
        });
      }
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const rules: ScenarioRuleInput[] = drafts.map(({ _key, ...rest }) => rest);
    put.mutate(
      { scenarioId, rules },
      { onSuccess: () => setDirty(false) },
    );
  };

  const columns = [
    {
      title: 'Роль',
      dataIndex: 'role',
      width: 160,
      render: (_: unknown, record: RuleDraft) => (
        <Select
          size="small"
          style={{ width: '100%' }}
          value={toRoleUi(record.role)}
          options={roleOptions}
          onChange={(v) => updateRow(record._key, { role: fromRoleUi(v) })}
        />
      ),
    },
    {
      title: 'Вид работ',
      dataIndex: 'work_type_id',
      render: (_: unknown, record: RuleDraft) => {
        const isDup = duplicateKeys.has(`${record.role ?? '__all__'}::${record.work_type_id}`);
        return (
          <Tooltip title={isDup ? 'Дубликат: роль + вид работ' : undefined} color="red">
            <Select
              size="small"
              style={{ width: '100%', borderColor: isDup ? 'red' : undefined }}
              status={isDup ? 'error' : undefined}
              value={record.work_type_id}
              options={workTypeOptions}
              onChange={(v) => updateRow(record._key, { work_type_id: v })}
            />
          </Tooltip>
        );
      },
    },
    {
      title: '% от нормы',
      dataIndex: 'percent_of_norm',
      width: 110,
      render: (_: unknown, record: RuleDraft) => (
        <InputNumber
          size="small"
          min={0}
          max={100}
          precision={1}
          style={{ width: '100%' }}
          value={record.percent_of_norm}
          onChange={(v) => updateRow(record._key, { percent_of_norm: v ?? 0 })}
        />
      ),
    },
    {
      title: '',
      width: 36,
      render: (_: unknown, record: RuleDraft) => (
        <Button
          type="text"
          danger
          size="small"
          icon={<DeleteOutlined />}
          onClick={() => removeRow(record._key)}
        />
      ),
    },
  ];

  const saveDisabled = !dirty || hasDuplicates || put.isPending;

  const handleCopy = () => {
    if (!copySourceId) return;
    const source = approvedScenarios.find((s) => s.id === copySourceId);
    copy.mutate(
      { scenarioId, sourceScenarioId: copySourceId },
      {
        onSuccess: (data) => {
          setCopyOpen(false);
          setDirty(false);
          const count = Array.isArray(data) ? data.length : 0;
          notification.success({
            title: `Скопировано правил: ${count}`,
            description: source ? `Из сценария «${source.name}»` : undefined,
          });
        },
        onError: (e) => notification.error({ title: 'Не удалось скопировать', description: (e as Error).message }),
      },
    );
  };

  const scenarioOptions = useMemo(
    () =>
      approvedScenarios
        .filter((s) => s.id !== scenarioId)
        .map((s) => {
          const q = s.quarter ?? '';
          const y = s.year ?? '';
          const team = s.team ? ` · ${s.team}` : '';
          return {
            value: s.id,
            label: `${s.name} (${q} ${y}${team})`.trim(),
          };
        }),
    [approvedScenarios, scenarioId],
  );

  const copyContent = (
    <Space orientation="vertical" size={8} style={{ width: 320 }}>
      <Select
        size="small"
        value={copySourceId}
        options={scenarioOptions}
        onChange={setCopySourceId}
        placeholder="Выберите сценарий"
        style={{ width: '100%' }}
        showSearch
        optionFilterProp="label"
        notFoundContent="Нет утверждённых сценариев"
      />
      <Button
        size="small"
        type="primary"
        block
        loading={copy.isPending}
        disabled={!copySourceId}
        onClick={handleCopy}
      >
        Скопировать
      </Button>
    </Space>
  );

  return (
    <Space orientation="vertical" size={8} style={{ width: '100%' }}>
      <Table<RuleDraft>
        size="small"
        dataSource={drafts}
        rowKey="_key"
        columns={columns}
        pagination={false}
        locale={{ emptyText: 'Нет правил' }}
      />
      <Space>
        <Button size="small" icon={<PlusOutlined />} onClick={addRow}>
          Добавить правило
        </Button>
        <Popover
          open={copyOpen}
          onOpenChange={setCopyOpen}
          content={copyContent}
          title="Скопировать правила из сценария"
          trigger="click"
        >
          <Button size="small" icon={<CopyOutlined />}>
            Из сценария
          </Button>
        </Popover>
        <Tooltip title={hasDuplicates ? 'Есть дубликаты — исправьте перед сохранением' : undefined}>
          <Button
            size="small"
            type="primary"
            icon={<SaveOutlined />}
            disabled={saveDisabled}
            loading={put.isPending}
            onClick={handleSave}
          >
            Сохранить
          </Button>
        </Tooltip>
        {dirty && (
          <Button size="small" onClick={handleReset}>
            Сбросить
          </Button>
        )}
      </Space>
    </Space>
  );
}
