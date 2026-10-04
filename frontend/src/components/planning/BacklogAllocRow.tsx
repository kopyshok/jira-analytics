import { memo, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { App, Checkbox, InputNumber, Select, Spin, Tag } from 'antd';
import type { SelectProps } from 'antd';
import { CaretDownOutlined, CaretUpOutlined, HolderOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { createLatestSaver } from '../../utils/latestSaver';
import { canStepPriority, parsePriorityInput, stepPriority } from '../../utils/priorityStep';
import { AllocationOverridePopover } from './AllocationOverridePopover';
import BacklogRoleCell from './BacklogRoleCell';
import { useScenarioAssigneeCandidates } from '../../hooks/usePlanning';
import { candidateOptions } from '../../utils/rpCandidates';
import { effectiveEstimate } from '../../utils/allocationEstimates';
import { statusTagColor } from '../../utils/status';
import { getRoleColor } from '../../utils/roles';
import { OPO_COLOR, foldOpo } from '../../utils/opo';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { AllocationResponse, Role } from '../../types/api';
import type { ContinuationInfoRow } from '../../api/planning';

export type BacklogAllocRowProps = {
  alloc: AllocationResponse;
  scenarioId: string;
  scenarioStatus: 'draft' | 'approved';
  isDraft: boolean;
  /** Включена сортировка по людям — строки не перетаскиваем. */
  dragLocked?: boolean;
  compact: boolean;
  flashing: boolean;
  rowStateClass: string;
  gridTemplate: string;
  gridGap: number;
  continuationInfo: ContinuationInfoRow | undefined;
  /** Состав команды сценария — список аналитика и разработчика, если кандидаты из всех команд не загрузились. */
  teamAssigneeOptions: { label: string; value: string }[];
  /** Группы команды. undefined — у команды нет деления, колонка не рисуется. */
  subgroupOptions?: { label: string; value: string }[];
  roles: Role[];
  /** Квартал сценария не раньше отсечки ОПЭ — колонки ОПЭ нет. */
  opoOff: boolean;
  jiraBaseUrl: string;
  resourceTotalForBacklog: number;
  registerRef: (id: string, el: HTMLDivElement | null) => void;
  onToggle: (a: AllocationResponse) => void;
  onPriorityChange: (backlogItemId: string, priority: number | null) => void | Promise<unknown>;
  onAssigneeChange: (allocId: string, employeeId: string | null) => void;
  onDeveloperChange: (allocId: string, employeeId: string | null) => void;
  onSubgroupChange?: (issueId: string, subgroupId: string | null) => void;
  onOpenBreakdown: (issueId: string, issueKey: string) => void;
};

type PriorityControlProps = {
  backlogItemId: string;
  priority: number | null;
  onChange: (backlogItemId: string, priority: number | null) => void | Promise<unknown>;
};

/** Приоритет: число (ручной ввод) и кнопки ▲ / ▼. Значение меняется сразу, сохранения идут по одному. */
function PriorityControl({ backlogItemId, priority, onChange }: PriorityControlProps) {
  const [value, setValue] = useState<number | null>(priority);
  const [resetKey, setResetKey] = useState(0);
  const cyan = value != null && value <= 3;
  const busyRef = useRef(false);
  const propRef = useRef(priority);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    propRef.current = priority;
    onChangeRef.current = onChange;
  });
  // Пока сохранение не закончилось, чужое значение из списка не затирает набранное.
  useEffect(() => {
    if (!busyRef.current) setValue(priority);
  }, [priority]);
  const pushRef = useRef<((v: number | null) => void) | null>(null);

  const commit = (next: number | null) => {
    if (next === value) return;
    setValue(next);
    busyRef.current = true;
    pushRef.current ??= createLatestSaver<number | null>(
      (v) => Promise.resolve(onChangeRef.current(backlogItemId, v)),
      (ok) => {
        busyRef.current = false;
        if (!ok) setValue(propRef.current);
      },
    );
    pushRef.current(next);
  };

  const arrow = (dir: 1 | -1): CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 16,
    height: 12,
    padding: 0,
    border: 'none',
    background: 'transparent',
    fontSize: 9,
    color: DARK_THEME.textMuted,
    cursor: canStepPriority(value, dir) ? 'pointer' : 'default',
    opacity: canStepPriority(value, dir) ? 1 : 0.25,
  });

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      <InputNumber
        key={resetKey}
        min={1}
        max={10}
        value={value}
        variant="borderless"
        size="small"
        controls={false}
        style={{
          width: 32,
          height: 24,
          borderRadius: 4,
          fontSize: 11,
          fontWeight: 700,
          fontFamily: FONTS.mono,
          color: cyan ? '#003a3a' : DARK_THEME.textMuted,
          background: cyan ? DARK_THEME.cyanPrimary : DARK_THEME.darkAccent,
          padding: 0,
          textAlign: 'center',
        }}
        className="backlog-priority-input"
        placeholder="—"
        onKeyDown={(e) => {
          if (e.key === 'Escape') (e.target as HTMLInputElement).blur();
        }}
        onBlur={(e) => {
          // Очистка поля не поддерживается: пустое возвращает прежнее значение.
          const raw = e.target.value;
          const next = parsePriorityInput(raw, value);
          if (raw === '') setResetKey((k) => k + 1); // перерисовать поле с прежним числом
          commit(next);
        }}
      />
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <button
          type="button"
          aria-label="Приоритет: прибавить 1"
          title="Прибавить 1"
          disabled={!canStepPriority(value, 1)}
          style={arrow(1)}
          onClick={() => commit(stepPriority(value, 1))}
        >
          <CaretUpOutlined />
        </button>
        <button
          type="button"
          aria-label="Приоритет: убавить 1"
          title="Убавить 1"
          disabled={!canStepPriority(value, -1)}
          style={arrow(-1)}
          onClick={() => commit(stepPriority(value, -1))}
        >
          <CaretDownOutlined />
        </button>
      </div>
    </div>
  );
}

type PersonSelectProps = {
  scenarioId: string;
  backlogItemId: string;
  phase: 'analyst' | 'dev';
  isDraft: boolean;
  value: string | null;
  displayName: string | null;
  /** Кто стоит в соседней колонке — его выбрать нельзя. */
  busyId: string | null;
  busyHint: string;
  teamAssigneeOptions: { label: string; value: string }[];
  roleLabels: ReadonlyMap<string, string>;
  onChange: (employeeId: string | null) => void;
};

/** Выбор человека строки — аналитика или разработчика. */
function PersonSelect({
  scenarioId, backlogItemId, phase, isDraft, value, displayName, busyId, busyHint,
  teamAssigneeOptions, roleLabels, onChange,
}: PersonSelectProps) {
  const { notification } = App.useApp();
  // Кандидаты — все, кто в квартале сценария состоит в какой-либо команде.
  // Грузятся, только пока список открыт: строк в сценарии много.
  const [open, setOpen] = useState(false);
  const candidates = useScenarioAssigneeCandidates(scenarioId, backlogItemId, open, phase);
  // Пока список не пришёл — одна опция с текущим; не загрузился — состав
  // команды сценария, как было до выбора из всех команд.
  const options = useMemo<SelectProps['options']>(
    () =>
      candidates.data?.length
        ? candidateOptions(candidates.data, roleLabels, { id: busyId, hint: busyHint })
        : candidates.isError
          ? teamAssigneeOptions.map((o) =>
              o.value === busyId ? { ...o, label: `${o.label} — ${busyHint}`, disabled: true } : o,
            )
          : value
            ? [{ value, label: displayName ?? '—' }]
            : [],
    [candidates.data, candidates.isError, roleLabels, busyId, busyHint, teamAssigneeOptions, value, displayName],
  );
  // Каждая неудачная загрузка списка — одно уведомление (с тем же ключом
  // повтор заменяет прежнее, а не копит стопку).
  const candidatesError = candidates.error;
  useEffect(() => {
    if (!candidatesError) return;
    notification.error({
      key: 'scenario-assignee-candidates',
      title: 'Не удалось загрузить список сотрудников',
      description: 'Показан состав команды сценария.',
    });
  }, [candidatesError, notification]);

  if (!isDraft && !value) {
    return <span style={{ fontSize: 12, color: DARK_THEME.textMuted }}>{displayName ?? '—'}</span>;
  }
  return (
    <Select
      size="small"
      value={value ?? undefined}
      placeholder={displayName ?? '—'}
      allowClear
      disabled={!isDraft}
      style={{ width: '100%', fontSize: 12 }}
      // Шире колонки: подпись с названием команды и загрузкой целиком
      // помещается почти у всех. Числом, а не false — иначе AntD
      // выключает виртуальный список.
      popupMatchSelectWidth={640}
      showSearch={{ optionFilterProp: 'label' }}
      loading={candidates.isFetching}
      notFoundContent={
        candidates.isFetching
          ? <Spin size="small" />
          : candidates.isError
            ? 'Не удалось загрузить список сотрудников'
            : undefined
      }
      options={options}
      onOpenChange={setOpen}
      // В закрытом поле — только имя; роль, команда и загрузка — в списке.
      labelRender={({ label }) => displayName ?? label}
      onChange={(v: string | undefined) => onChange(v ?? null)}
    />
  );
}

function BacklogAllocRowBase({
  alloc: a,
  scenarioId,
  scenarioStatus,
  isDraft,
  dragLocked = false,
  compact,
  flashing,
  rowStateClass,
  gridTemplate,
  gridGap,
  continuationInfo,
  teamAssigneeOptions,
  subgroupOptions,
  roles,
  opoOff,
  jiraBaseUrl,
  resourceTotalForBacklog,
  registerRef,
  onToggle,
  onPriorityChange,
  onAssigneeChange,
  onDeveloperChange,
  onSubgroupChange,
  onOpenBreakdown,
}: BacklogAllocRowProps) {
  const { setNodeRef, transform, transition, isDragging, attributes, listeners } = useSortable({ id: a.id });

  const setRowRef = useCallback(
    (el: HTMLDivElement | null) => {
      setNodeRef(el);
      registerRef(a.id, el);
    },
    [setNodeRef, registerRef, a.id],
  );

  const roleLabels = useMemo(
    () => new Map(roles.map((r) => [r.code, r.label] as const)),
    [roles],
  );

  const raw = effectiveEstimate(a);
  // С квартала отсечки часы ОПЭ показываем внутри АН и ПР.
  const eff = opoOff ? foldOpo(raw, a.opo_analyst_ratio) : raw;
  const an = eff.analyst;
  const de = eff.dev;
  const qa = eff.qa;
  const op = eff.opo;
  const total = an + de + qa + op;
  const canDrag = isDraft && !dragLocked;
  const hasOverride =
    a.override_estimate_analyst_hours !== null ||
    a.override_estimate_dev_hours !== null ||
    a.override_estimate_qa_hours !== null ||
    a.override_estimate_opo_hours !== null;
  const isPendingContinuation = !!continuationInfo?.is_continuation && !hasOverride;

  const className = ['backlog-row', flashing ? 'cyan-flash' : '', rowStateClass]
    .filter(Boolean)
    .join(' ');

  // Мягкая подсветка отмеченных: лёгкий cyan-фон + 3px акцентная полоса слева.
  // Неотмеченные — прозрачный фон, opacity 0.85 (чуть выше чем было 0.7 — для
  // читаемости при демо без визуального шума).
  const style: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: gridTemplate,
    columnGap: gridGap,
    padding: compact ? '4px 14px' : '12px 14px',
    fontSize: compact ? 13 : 14,
    borderBottom: `1px solid ${DARK_THEME.border}`,
    alignItems: 'center',
    cursor: isDraft ? 'pointer' : 'default',
    background: a.included
      ? 'var(--row-included-bg, rgba(0,201,200,0.06))'
      : 'transparent',
    borderLeft: a.included
      ? '3px solid var(--accent-1, #00c9c8)'
      : '3px solid transparent',
    opacity: a.included ? 1 : 0.85,
    transform: CSS.Translate.toString(transform),
    transition,
    ...(isDragging ? { opacity: 0.5 } : null),
  };

  return (
    <div data-flip-wrapper="" data-alloc-id={a.id}>
    <div
      ref={setRowRef}
      onClick={() => onToggle(a)}
      className={className}
      style={style}
    >
      <span
        {...(canDrag ? attributes : {})}
        {...(canDrag ? listeners : {})}
        onClick={(e) => e.stopPropagation()}
        title={dragLocked && isDraft ? 'Сброс сортировки — щелчок по заголовку' : isDraft ? 'Перетащить' : ''}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: canDrag ? 'grab' : 'default',
          color: DARK_THEME.textMuted,
          opacity: canDrag ? 1 : 0.3,
          touchAction: 'none',
        }}
      >
        <HolderOutlined />
      </span>
      <div onClick={(e) => e.stopPropagation()}>
        <Checkbox checked={a.included} disabled={!isDraft} onChange={() => onToggle(a)} />
      </div>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <PriorityControl
          backlogItemId={a.backlog_item_id}
          priority={a.priority}
          onChange={onPriorityChange}
        />
      </div>
      <div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            color: DARK_THEME.textPrimary,
            fontSize: 14,
            marginBottom: 3,
          }}
        >
          <span style={{ flex: '1 1 auto', minWidth: 0 }}>{a.title}</span>
          {hasOverride && (
            <Tag color="gold" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>
              переоценка
            </Tag>
          )}
          {isPendingContinuation && (
            <Tag color="red" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>
              ⚠ продолжение
            </Tag>
          )}
          <AllocationOverridePopover
            scenarioId={scenarioId}
            allocationId={a.id}
            scenarioStatus={scenarioStatus}
            currentOverride={{
              analyst: a.override_estimate_analyst_hours,
              dev: a.override_estimate_dev_hours,
              qa: a.override_estimate_qa_hours,
              opo: a.override_estimate_opo_hours,
            }}
            continuation={continuationInfo}
            opoOff={opoOff}
            opoAnalystRatio={a.opo_analyst_ratio}
          />
        </div>
        {a.status && (
          <Tag
            color={statusTagColor(a.status, a.status_category)}
            style={{ fontSize: 10, margin: '2px 4px 0 0', padding: '0 4px' }}
          >
            {a.status}
          </Tag>
        )}
        {a.jira_key &&
          (jiraBaseUrl ? (
            <a
              href={`${jiraBaseUrl}/browse/${a.jira_key}`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              style={{ fontFamily: FONTS.mono, fontSize: 11, color: DARK_THEME.cyanSecondary }}
            >
              {a.jira_key}
            </a>
          ) : (
            <span style={{ fontFamily: FONTS.mono, fontSize: 11, color: DARK_THEME.cyanSecondary }}>
              {a.jira_key}
            </span>
          ))}
        {a.has_children_in_backlog && a.issue_id && (
          <InfoCircleOutlined
            onClick={(e) => {
              e.stopPropagation();
              onOpenBreakdown(a.issue_id!, a.jira_key ?? '');
            }}
            style={{ marginLeft: 6, cursor: 'pointer', color: '#38bdf8', fontSize: 13 }}
          />
        )}
        {a.cost_type && (
          <Tag
            color={a.cost_type.toLowerCase().includes('change') ? 'blue' : 'green'}
            style={{ fontSize: 10, padding: '0 4px', marginLeft: 4 }}
          >
            {a.cost_type}
          </Tag>
        )}
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <PersonSelect
          scenarioId={scenarioId}
          backlogItemId={a.backlog_item_id}
          phase="analyst"
          isDraft={isDraft}
          value={a.assignee_employee_id}
          displayName={a.assignee_display_name}
          busyId={a.developer_employee_id}
          busyHint="уже разработчик этой задачи"
          teamAssigneeOptions={teamAssigneeOptions}
          roleLabels={roleLabels}
          onChange={(id) => onAssigneeChange(a.id, id)}
        />
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <PersonSelect
          scenarioId={scenarioId}
          backlogItemId={a.backlog_item_id}
          phase="dev"
          isDraft={isDraft}
          value={a.developer_employee_id}
          displayName={a.developer_display_name}
          busyId={a.assignee_employee_id}
          busyHint="уже аналитик этой задачи"
          teamAssigneeOptions={teamAssigneeOptions}
          roleLabels={roleLabels}
          onChange={(id) => onDeveloperChange(a.id, id)}
        />
      </div>
      {subgroupOptions && (
        <div onClick={(e) => e.stopPropagation()}>
          {/* Группа пишется на саму задачу — идея без задачи её хранить негде. */}
          <Select
            size="small"
            value={a.subgroup_id ?? undefined}
            placeholder="—"
            allowClear
            disabled={!isDraft || !a.issue_id}
            style={{ width: '100%', fontSize: 12 }}
            options={subgroupOptions}
            onChange={(value: string | undefined) =>
              a.issue_id && onSubgroupChange?.(a.issue_id, value ?? null)
            }
          />
        </div>
      )}
      <div
        style={{
          fontSize: 12,
          color: DARK_THEME.textMuted,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {a.customer ?? '—'}
      </div>
      <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
        <BacklogRoleCell label="АН" hours={an} total={total} color={getRoleColor(roles, 'analyst')} />
        <BacklogRoleCell label="ПР" hours={de} total={total} color={getRoleColor(roles, 'dev')} />
        <BacklogRoleCell label="ТС" hours={qa} total={total} color={getRoleColor(roles, 'qa')} />
        {!opoOff && (
          <BacklogRoleCell label="ОПЭ" hours={op} total={total} color={OPO_COLOR} />
        )}
      </div>
      <div style={{ textAlign: 'right' }}>
        <span style={{ fontFamily: FONTS.mono, fontSize: 14, color: DARK_THEME.textPrimary }}>
          {Math.round(total)} ч
        </span>
        {resourceTotalForBacklog > 0 && (
          <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 1 }}>
            {Math.round((total / resourceTotalForBacklog) * 100)}% ресурса
          </div>
        )}
      </div>
    </div>
    </div>
  );
}

const BacklogAllocRow = memo(BacklogAllocRowBase);
export default BacklogAllocRow;
