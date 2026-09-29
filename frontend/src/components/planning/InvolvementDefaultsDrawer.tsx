import { useState } from 'react';
import {
  App, Button, Drawer, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Typography,
} from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import {
  useInvolvementDefaults,
  useCreateInvolvementDefault,
  useDeleteInvolvementDefault,
} from '../../hooks/useInvolvementDefaults';
import {
  usePersonalSettings,
  useCreatePersonalSetting,
  useUpdatePersonalSetting,
  useDeletePersonalSetting,
} from '../../hooks/usePersonalSettings';
import { useOpoCutoff } from '../../hooks/useOpoCutoff';
import { useScenarioResource, useScenarioRules } from '../../hooks/usePlanning';
import { useMandatoryWorkTypes } from '../../hooks/useCapacity';
import {
  formatInvolvement, formatNormed, formatQuarter, roleNormedPercents, sumPercent,
} from '../../utils/personalSettings';
import type { PersonalSetting, PersonalSettingInput, ScenarioRuleOut } from '../../types/api';

const ROLE_LABELS: Record<string, string> = {
  analyst: 'Анализ',
  dev: 'Разработка',
  qa: 'Тестирование',
  opo: 'ОПЭ',
};
const ALL_ROLE_OPTIONS = Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }));
const QUARTER_OPTIONS = [1, 2, 3, 4].map((q) => ({ value: q, label: `Q${q}` }));

/** После правки/удаления личной настройки раскладку нужно пересчитать вручную. */
const REASSIGN_HINT = 'Чтобы раскладка учла изменение, нажмите «Распределить» в ресурсном плане';

interface EmployeeOption {
  label: string;
  value: string;
  role: string | null;
}

/** Модальная форма записи сотрудника: добавление или правка. */
function PersonalSettingModal({
  row, employeeOptions, scenarioRules, normedWorkTypes, onClose, onSubmit, submitting,
}: {
  row: PersonalSetting | null;
  employeeOptions: EmployeeOption[];
  scenarioRules: ScenarioRuleOut[];
  normedWorkTypes: { id: string; label: string }[];
  onClose: () => void;
  onSubmit: (body: PersonalSettingInput) => void;
  submitting: boolean;
}) {
  const isEdit = row != null;
  const now = new Date();
  const [employeeId, setEmployeeId] = useState<string | undefined>(row?.employee_id);
  const [year, setYear] = useState<number>(row?.effective_year ?? now.getFullYear());
  const [quarter, setQuarter] = useState<number>(row?.effective_quarter ?? 1);
  const [involvementPct, setInvolvementPct] = useState<number | null>(
    row?.involvement != null ? Math.round(row.involvement * 100) : null,
  );
  const [normedCustom, setNormedCustom] = useState<boolean>(row?.normed_custom ?? false);
  const [percents, setPercents] = useState<Record<string, number>>(() => {
    const m: Record<string, number> = {};
    for (const n of row?.normed ?? []) m[n.work_type_id] = n.percent_of_norm;
    return m;
  });
  // Сохранённые «свои» проценты (isEdit) и любая правка пользователя — сохранить
  // при переключении «свои» выкл/вкл и не затирать при смене сотрудника.
  const [touched, setTouched] = useState<boolean>(isEdit && row?.normed_custom === true);

  // Бывший участник команды может отсутствовать среди текущих employeeOptions —
  // тогда добавляем его самого, иначе disabled-Select при правке покажет id.
  const options = row && !employeeOptions.some((o) => o.value === row.employee_id)
    ? [...employeeOptions, { label: row.employee_name, value: row.employee_id, role: row.employee_role }]
    : employeeOptions;

  const employeeRole = employeeOptions.find((o) => o.value === employeeId)?.role
    ?? row?.employee_role ?? null;

  const poolWorkTypeIds = normedWorkTypes.map((wt) => wt.id);

  const prefillFor = (role: string | null) => {
    const prefill = roleNormedPercents(scenarioRules, role, poolWorkTypeIds);
    const m: Record<string, number> = {};
    for (const wt of normedWorkTypes) m[wt.id] = prefill[wt.id] ?? 0;
    return m;
  };

  // Переключение на «свои» подставляет проценты правил роли сотрудника из
  // текущего сценария — но только если пользователь ещё ничего не вводил и
  // не редактирует уже сохранённые «свои» значения.
  const handleToggleCustom = (checked: boolean) => {
    setNormedCustom(checked);
    if (checked && !touched) {
      setPercents(prefillFor(employeeRole));
    }
  };

  // Смена сотрудника (доступна только при добавлении новой записи) переигрывает
  // подстановку под роль нового сотрудника — но лишь пока значения не тронуты.
  const handleEmployeeChange = (value: string) => {
    setEmployeeId(value);
    if (normedCustom && !touched) {
      const role = employeeOptions.find((o) => o.value === value)?.role ?? null;
      setPercents(prefillFor(role));
    }
  };

  const handlePercentChange = (workTypeId: string, v: number | null) => {
    setTouched(true);
    setPercents((prev) => ({ ...prev, [workTypeId]: v ?? 0 }));
  };

  const rows = normedWorkTypes.map((wt) => ({
    work_type_id: wt.id,
    label: wt.label,
    percent_of_norm: percents[wt.id] ?? 0,
  }));
  const total = sumPercent(rows);
  const canSubmit = !!employeeId && !!year && !!quarter;

  const handleOk = () => {
    if (!employeeId) return;
    onSubmit({
      employee_id: employeeId,
      effective_year: year,
      effective_quarter: quarter,
      involvement: involvementPct == null ? null : involvementPct / 100,
      normed_custom: normedCustom,
      normed: normedCustom
        ? rows
          .filter((r) => r.percent_of_norm > 0)
          .map((r) => ({ work_type_id: r.work_type_id, percent_of_norm: r.percent_of_norm }))
        : [],
    });
  };

  return (
    <Modal
      title={isEdit ? 'Изменить запись' : 'Добавить сотрудника'}
      open
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={submitting}
      okButtonProps={{ disabled: !canSubmit }}
      okText={isEdit ? 'Сохранить' : 'Добавить'}
      cancelText="Отмена"
      destroyOnHidden
      width={520}
    >
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <div>
          <label htmlFor="personal-setting-employee" style={{ display: 'block', marginBottom: 4 }}>
            Сотрудник
          </label>
          <Select
            id="personal-setting-employee"
            style={{ width: '100%' }}
            placeholder="Выберите сотрудника"
            value={employeeId}
            onChange={handleEmployeeChange}
            options={options}
            disabled={isEdit}
            showSearch
            optionFilterProp="label"
          />
        </div>
        <Space wrap size={16}>
          <div>
            <label htmlFor="personal-setting-year" style={{ display: 'block', marginBottom: 4 }}>Год</label>
            <InputNumber
              id="personal-setting-year"
              value={year}
              onChange={(v) => setYear(v ?? year)}
              min={2000}
              max={2100}
              disabled={isEdit}
              style={{ width: 110 }}
            />
          </div>
          <div>
            <label htmlFor="personal-setting-quarter" style={{ display: 'block', marginBottom: 4 }}>Квартал</label>
            <Select
              id="personal-setting-quarter"
              style={{ width: 90 }}
              value={quarter}
              onChange={setQuarter}
              options={QUARTER_OPTIONS}
              disabled={isEdit}
            />
          </div>
          <div>
            <label htmlFor="personal-setting-involvement" style={{ display: 'block', marginBottom: 4 }}>
              Вовлечённость, %
            </label>
            <InputNumber
              id="personal-setting-involvement"
              style={{ width: 140 }}
              value={involvementPct}
              onChange={setInvolvementPct}
              min={1}
              max={100}
              placeholder="как обычно"
            />
          </div>
        </Space>
        <Space align="center">
          <Typography.Text type={normedCustom ? 'secondary' : undefined}>по правилам роли</Typography.Text>
          <Switch
            checked={normedCustom}
            onChange={handleToggleCustom}
            aria-label="Нормированные работы: по правилам роли или свои"
          />
          <Typography.Text type={normedCustom ? undefined : 'secondary'}>свои</Typography.Text>
        </Space>
        {normedCustom && (
          <div>
            <Space orientation="vertical" size={6} style={{ width: '100%' }}>
              {normedWorkTypes.map((wt) => (
                <Space key={wt.id} style={{ width: '100%', justifyContent: 'space-between' }}>
                  <label htmlFor={`personal-setting-normed-${wt.id}`}>{wt.label}</label>
                  <InputNumber
                    id={`personal-setting-normed-${wt.id}`}
                    size="small"
                    min={0}
                    max={100}
                    value={percents[wt.id] ?? 0}
                    onChange={(v) => handlePercentChange(wt.id, v)}
                    style={{ width: 90 }}
                    suffix="%"
                  />
                </Space>
              ))}
            </Space>
            <div style={{ marginTop: 8 }}>
              <Typography.Text type={total > 100 ? 'danger' : 'secondary'}>
                Сумма: {total}%{total > 100 ? ' — больше 100%' : ''}
              </Typography.Text>
            </div>
          </div>
        )}
      </Space>
    </Modal>
  );
}

export default function InvolvementDefaultsDrawer({
  open, onClose, team, scenarioId,
}: {
  open: boolean;
  onClose: () => void;
  team: string | null;
  scenarioId?: string | null;
}) {
  const { notification, modal } = App.useApp();
  const { opoOffNow } = useOpoCutoff();
  const roleOptions = opoOffNow
    ? ALL_ROLE_OPTIONS.filter((o) => o.value !== 'opo')
    : ALL_ROLE_OPTIONS;
  const { data: allRows = [], isLoading } = useInvolvementDefaults(team);
  const data = opoOffNow
    ? allRows.filter((r) => r.role !== 'opo')
    : allRows;
  const create = useCreateInvolvementDefault();
  const del = useDeleteInvolvementDefault();

  const now = new Date();
  const [role, setRole] = useState('analyst');
  const [year, setYear] = useState<number>(now.getFullYear());
  const [quarter, setQuarter] = useState<number>(1);
  const [valuePct, setValuePct] = useState<number | null>(80);

  const handleAdd = () => {
    if (!team || valuePct == null) return;
    create.mutate(
      { team, role, effective_year: year, effective_quarter: quarter, involvement: valuePct / 100 },
      {
        onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
      },
    );
  };

  const columns = [
    { title: 'Роль', dataIndex: 'role', render: (r: string) => ROLE_LABELS[r] ?? r },
    {
      title: 'Действует с',
      key: 'eff',
      render: (_: unknown, row: { effective_quarter: number; effective_year: number }) =>
        `Q${row.effective_quarter} ${row.effective_year}`,
    },
    { title: 'Вовлечённость', dataIndex: 'involvement' },
    {
      title: '',
      key: 'act',
      width: 48,
      render: (_: unknown, row: { id: string }) => (
        <Popconfirm title="Удалить?" onConfirm={() => del.mutate(row.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} aria-label="Удалить запись" />
        </Popconfirm>
      ),
    },
  ];

  // ── Сотрудники: личная вовлечённость и нормированные работы ──
  const { data: personalRows = [], isLoading: personalLoading } = usePersonalSettings(team);
  const { data: resourceBase } = useScenarioResource(scenarioId ?? undefined, !!scenarioId);
  const { data: scenarioRules = [] } = useScenarioRules(scenarioId ?? undefined);
  const { data: workTypes = [] } = useMandatoryWorkTypes({ isActive: true });
  const normedWorkTypes = workTypes.filter((wt) => wt.subtracts_from_pool);
  const employeeOptions: EmployeeOption[] = (resourceBase?.employees ?? []).map((e) => ({
    label: e.display_name,
    value: e.employee_id,
    role: e.role,
  }));

  const createPersonal = useCreatePersonalSetting();
  const updatePersonal = useUpdatePersonalSetting();
  const deletePersonal = useDeletePersonalSetting();
  const [modalRow, setModalRow] = useState<PersonalSetting | 'new' | null>(null);

  const notifyReassign = () => notification.success({ title: REASSIGN_HINT });

  const handlePersonalSubmit = (body: PersonalSettingInput) => {
    const opts = {
      onSuccess: () => {
        setModalRow(null);
        notifyReassign();
      },
      onError: (e: Error) => notification.error({ title: 'Ошибка', description: e.message }),
    };
    if (modalRow === 'new') createPersonal.mutate(body, opts);
    else if (modalRow) updatePersonal.mutate({ id: modalRow.id, body }, opts);
  };

  const handlePersonalDelete = (row: PersonalSetting) => {
    modal.confirm({
      title: 'Удалить запись?',
      content: `${row.employee_name}, ${formatQuarter(row.effective_year, row.effective_quarter)}`,
      okText: 'Удалить',
      cancelText: 'Отмена',
      okButtonProps: { danger: true },
      onOk: () => deletePersonal.mutate(row.id, {
        onSuccess: notifyReassign,
        onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
      }),
    });
  };

  const personalColumns = [
    { title: 'Сотрудник', dataIndex: 'employee_name' },
    {
      title: 'С квартала',
      key: 'eff',
      render: (_: unknown, row: PersonalSetting) => formatQuarter(row.effective_year, row.effective_quarter),
    },
    {
      title: 'Вовлечённость',
      key: 'involvement',
      render: (_: unknown, row: PersonalSetting) => formatInvolvement(row.involvement),
    },
    {
      title: 'Нормированные работы',
      key: 'normed',
      render: (_: unknown, row: PersonalSetting) => formatNormed(row),
    },
    {
      title: '',
      key: 'act',
      width: 88,
      render: (_: unknown, row: PersonalSetting) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => setModalRow(row)}
            aria-label="Изменить запись"
          />
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handlePersonalDelete(row)}
            aria-label="Удалить запись"
          />
        </Space>
      ),
    },
  ];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      styles={{ wrapper: { width: 640 } }}
      title="Вовлечённость и нормированные работы"
    >
      {!team ? (
        <div>Выберите команду сценария.</div>
      ) : (
        <Space orientation="vertical" size={24} style={{ width: '100%' }}>
          <div>
            <Typography.Title level={5}>По ролям команды</Typography.Title>
            <Space orientation="vertical" size={16} style={{ width: '100%' }}>
              <Space wrap>
                <Select style={{ width: 150 }} value={role} onChange={setRole} options={roleOptions} />
                <Select style={{ width: 90 }} value={quarter} onChange={setQuarter} options={QUARTER_OPTIONS} />
                <InputNumber style={{ width: 100 }} value={year} onChange={(v) => setYear(v ?? year)} min={2000} max={2100} />
                <InputNumber
                  style={{ width: 110 }}
                  value={valuePct}
                  onChange={setValuePct}
                  min={0}
                  max={100}
                  step={5}
                  suffix="%"
                  placeholder="0–100"
                />
                <Button type="primary" icon={<PlusOutlined />} loading={create.isPending} onClick={handleAdd}>
                  Добавить
                </Button>
              </Space>
              <Table
                rowKey="id"
                size="small"
                loading={isLoading}
                dataSource={data}
                columns={columns}
                pagination={false}
              />
            </Space>
          </div>

          <div>
            <Typography.Title level={5}>Сотрудники</Typography.Title>
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
              Личная настройка действует в планах и сценариях любой команды сотрудника
            </Typography.Text>
            <Space orientation="vertical" size={16} style={{ width: '100%' }}>
              <Button icon={<PlusOutlined />} onClick={() => setModalRow('new')}>
                Добавить
              </Button>
              <Table
                rowKey="id"
                size="small"
                loading={personalLoading}
                dataSource={personalRows}
                columns={personalColumns}
                pagination={false}
              />
            </Space>
          </div>
        </Space>
      )}
      {modalRow && (
        <PersonalSettingModal
          row={modalRow === 'new' ? null : modalRow}
          employeeOptions={employeeOptions}
          scenarioRules={scenarioRules}
          normedWorkTypes={normedWorkTypes}
          onClose={() => setModalRow(null)}
          onSubmit={handlePersonalSubmit}
          submitting={createPersonal.isPending || updatePersonal.isPending}
        />
      )}
    </Drawer>
  );
}
