import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import {
  Alert, App, Badge, Button, Card, Checkbox, Popconfirm, Select, Space, Tag, Tooltip,
} from 'antd';
import {
  CheckCircleOutlined, CheckSquareTwoTone, ClockCircleOutlined, CompressOutlined,
  DeleteOutlined, FlagFilled, PlusOutlined, ReloadOutlined, RollbackOutlined,
  ShopOutlined, UserOutlined,
} from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import PlanningCapacityPanel from '../components/planning/PlanningCapacityPanel';
import ScenarioCreateModal from '../components/planning/ScenarioCreateModal';
import ScenarioRulesEditor from '../components/planning/ScenarioRulesEditor';
import ExternalQaInput from '../components/planning/ExternalQaInput';
import ScenarioResourceSummary from '../components/planning/ScenarioResourceSummary';
import BacklogRoleCell from '../components/planning/BacklogRoleCell';
import {
  useScenarios,
  useScenario,
  useScenarioAllocations,
  usePatchAllocation,
  useDeleteScenario,
  useApproveScenario,
  useRevertScenario,
  useSyncScenarioBacklog,
  useScenarioResource,
  useScenarioResourceSummary,
  useUpdateScenario,
  usePatchAllocationAssignee,
} from '../hooks/usePlanning';
import { TeamSelector } from '../components/planning/TeamSelector';
import { downloadScenarioXlsx } from '../api/exports';
import { DARK_THEME, FONTS } from '../utils/constants';
import { useRoles } from '../hooks/useRoles';
import { useJiraSettings } from '../hooks/useSettings';
import { getRoleColor } from '../utils/roles';
import { OPO_COLOR } from '../utils/opo';
import type { AllocationResponse } from '../types/api';

const GRID = '36px 48px minmax(0, 1fr) 150px 180px 260px 90px';
const GRID_GAP = 8;

function rolesAffectedByAllocation(
  a: AllocationResponse,
  employees: { employee_id: string; role: string | null }[] | undefined,
): string[] {
  const ea = a.estimate_analyst_hours ?? 0;
  const ed = a.estimate_dev_hours ?? 0;
  const eq = a.estimate_qa_hours ?? 0;
  const eo = a.estimate_opo_hours ?? 0;
  const r = a.opo_analyst_ratio ?? 0.5;
  const emp = employees?.find((e) => e.employee_id === a.assignee_employee_id);
  const role = emp?.role ?? a.assignee_role ?? null;
  const isAnalystSubstitute =
    role === 'RP' || role === 'project_manager' || role === 'consultant';
  const analystTarget = isAnalystSubstitute ? (role as string) : 'analyst';
  const out: string[] = [];
  if (ea + eo * r > 0) out.push(analystTarget);
  if (ed + eo * (1 - r) > 0) out.push('dev');
  if (eq > 0) out.push('qa');
  return out;
}

export default function PlanningPage() {
  const { notification } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'distribution' | 'rules'>('distribution');
  const [compact, setCompact] = useState<boolean>(
    () => localStorage.getItem('planning_backlog_compact') === 'true',
  );
  const toggleCompact = () => {
    setCompact((prev) => {
      const next = !prev;
      localStorage.setItem('planning_backlog_compact', String(next));
      return next;
    });
  };

  const [flashingIds, setFlashingIds] = useState<Set<string>>(() => new Set());

  const flashRow = (allocId: string) => {
    setFlashingIds((prev) => {
      const next = new Set(prev);
      next.add(allocId);
      return next;
    });
    setTimeout(() => {
      setFlashingIds((prev) => {
        const next = new Set(prev);
        next.delete(allocId);
        return next;
      });
    }, 650);
  };

  const [pulsedRoles, setPulsedRoles] = useState<Set<string>>(() => new Set());

  const pulseRoles = (roles: string[]) => {
    if (roles.length === 0) return;
    setPulsedRoles((prev) => {
      const next = new Set(prev);
      roles.forEach((r) => next.add(r));
      return next;
    });
    setTimeout(() => {
      setPulsedRoles((prev) => {
        const next = new Set(prev);
        roles.forEach((r) => next.delete(r));
        return next;
      });
    }, 600);
  };

  const scenarioId = searchParams.get('scenario') || null;
  const setScenarioId = (id: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (id) next.set('scenario', id);
    else next.delete('scenario');
    setSearchParams(next, { replace: true });
  };

  const { data: roles = [] } = useRoles();
  const jiraSettings = useJiraSettings();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';
  const { data: scenarios } = useScenarios();
  const { data: scenario } = useScenario(scenarioId);
  const { data: allocations, isLoading: allocLoading } =
    useScenarioAllocations(scenarioId);

  const patchAlloc = usePatchAllocation();
  const patchAssignee = usePatchAllocationAssignee();
  const updateScenario = useUpdateScenario();
  const deleteScenario = useDeleteScenario();
  const approve = useApproveScenario();
  const revert = useRevertScenario();
  const syncBacklog = useSyncScenarioBacklog();

  // Запоминаем id, который сейчас удаляется, — иначе авто-выбор ниже успеет
  // снова взять его из стейл-кэша списка между `setScenarioId(null)` и
  // refetch'ем, и лечит 404 на useScenario/useScenarioAllocations.
  const deletingIdRef = useRef<string | null>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // Авто-выбор: если сценарий из URL исчез (удалили) либо не выбран — взять
  // первый доступный, кроме того, что сейчас в процессе удаления.
  useEffect(() => {
    if (!scenarios) return;
    const available = scenarios.filter((s) => s.id !== deletingIdRef.current);
    if (scenarioId && !available.some((s) => s.id === scenarioId)) {
      setScenarioId(available[0]?.id ?? null);
      return;
    }
    if (!scenarioId && available.length > 0) {
      setScenarioId(available[0].id);
    }
  }, [scenarioId, scenarios]); // eslint-disable-line react-hooks/exhaustive-deps

  const includedIds = useMemo(
    () => (allocations ?? []).filter((a) => a.included).map((a) => a.backlog_item_id),
    [allocations],
  );

  const quarterInt = useMemo(() => {
    if (!scenario?.quarter) return 0;
    const m = scenario.quarter.match(/Q(\d)/);
    return m ? Number(m[1]) : 0;
  }, [scenario]);

  // Ресурс команды — не зависит от конкретных включённых идей, грузится один раз.
  // Не дёргаем ручку пока у сценария не выбрана команда — иначе бэк вернёт 400.
  const { data: resourceBase } = useScenarioResource(
    scenarioId ?? undefined,
    !!scenario?.team,
  );

  const { data: resourceSummary } = useScenarioResourceSummary(
    scenarioId ?? '',
    !!scenario?.team,
  );

  const isDraft = scenario?.status === 'draft';
  const isApproved = scenario?.status === 'approved';

  const scrollRowIntoView = (allocId: string) => {
    const el = rowRefs.current.get(allocId);
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const fullyVisible = rect.top >= 60 && rect.bottom <= window.innerHeight - 20;
    if (!fullyVisible) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  const toggleAllocation = (alloc: AllocationResponse) => {
    if (!scenarioId || !isDraft) return;
    flashRow(alloc.id);
    pulseRoles(rolesAffectedByAllocation(alloc, resourceBase?.employees));
    scrollRowIntoView(alloc.id);
    patchAlloc.mutate(
      { scenarioId, allocId: alloc.id, data: { included: !alloc.included } },
      { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
    );
  };

  const handleApprove = () => {
    if (!scenarioId) return;
    approve.mutate(scenarioId, {
      onSuccess: () => notification.success({ title: 'Сценарий утверждён' }),
      onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const handleRevert = () => {
    if (!scenarioId) return;
    revert.mutate(scenarioId, {
      onSuccess: () => notification.success({ title: 'Возвращено в черновик' }),
      onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const handleDelete = () => {
    if (!scenarioId) return;
    const id = scenarioId;
    deletingIdRef.current = id;
    setScenarioId(null);
    deleteScenario.mutate(id, {
      onSuccess: () => {
        notification.success({ title: 'Сценарий удалён' });
        deletingIdRef.current = null;
      },
      onError: (e) => {
        deletingIdRef.current = null;
        notification.error({ title: 'Ошибка', description: (e as Error).message });
      },
    });
  };

  const handleSync = () => {
    if (!scenarioId) return;
    syncBacklog.mutate(scenarioId, {
      onSuccess: () => notification.success({ title: 'Синхронизировано с бэклогом' }),
      onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const handleTeamChange = (team: string | null) => {
    if (!scenarioId) return;
    updateScenario.mutate(
      { id: scenarioId, data: { team } },
      { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
    );
  };

  const scenarioOptions = useMemo(
    () => (scenarios ?? []).map((s) => ({
      value: s.id,
      label: `${s.name} · ${s.quarter ?? ''} ${s.year ?? ''}${s.status === 'approved' ? ' ✓' : ''}`,
    })),
    [scenarios],
  );

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <div style={{ marginBottom: -36 }}>
      <PageHeader
        eyebrow="Планирование"
        title="Сценарии"
        subtitle="Отметьте галочками задачи из бэклога — сформируется план квартала"
        actions={
          <Space>
            <Select
              style={{ minWidth: 320 }}
              placeholder="Выберите сценарий"
              value={scenarioId ?? undefined}
              onChange={(v) => setScenarioId(v)}
              options={scenarioOptions}
              allowClear
              onClear={() => setScenarioId(null)}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              Новый сценарий
            </Button>
          </Space>
        }
      />
      </div>

      <ScenarioCreateModal
        open={createOpen}
        onClose={(createdId) => {
          setCreateOpen(false);
          if (createdId) setScenarioId(createdId);
        }}
      />

      {!scenarioId && (
        <Card>
          <div style={{ textAlign: 'center', padding: 40, color: DARK_THEME.textMuted }}>
            Сценарии отсутствуют или не выбраны. Нажмите «Новый сценарий», чтобы
            начать планирование квартала.
          </div>
        </Card>
      )}

      {scenarioId && scenario && !scenario.team && (
        <Card>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Alert
              type="info"
              message="Для работы со сценарием выберите команду"
              description="Сценарий привязан к конкретной команде — именно по ней считается ресурс и загрузка."
              showIcon
            />
            <TeamSelector
              value={scenario.team || null}
              onChange={handleTeamChange}
            />
          </Space>
        </Card>
      )}

      {scenarioId && scenario && !!scenario.team && (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Card
            styles={{ body: { padding: '14px 18px' } }}
            style={{ background: DARK_THEME.cardBg }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 18, fontWeight: 600, color: DARK_THEME.textPrimary }}>
                  {scenario.name}
                </span>
                <span style={{ color: DARK_THEME.textMuted, fontFamily: FONTS.mono, fontSize: 13 }}>
                  {scenario.quarter} {scenario.year}
                </span>
                <Badge
                  status={isApproved ? 'success' : 'processing'}
                  text={isApproved ? 'Утверждён' : 'Черновик'}
                />
                {allocations && (
                  <span style={{ color: DARK_THEME.textHint, fontSize: 12 }}>
                    включено {includedIds.length} из {allocations.length}
                  </span>
                )}
              </div>
              <Space>
                {isDraft && (
                  <Tooltip title="Досоздать allocations для новых элементов бэклога">
                    <Button
                      icon={<ReloadOutlined />}
                      size="small"
                      onClick={handleSync}
                      loading={syncBacklog.isPending}
                    >
                      Синк с бэклогом
                    </Button>
                  </Tooltip>
                )}
                {isDraft ? (
                  <Button
                    type="primary"
                    icon={<CheckCircleOutlined />}
                    size="small"
                    onClick={handleApprove}
                    loading={approve.isPending}
                  >
                    Утвердить
                  </Button>
                ) : (
                  <Button
                    icon={<RollbackOutlined />}
                    size="small"
                    onClick={handleRevert}
                    loading={revert.isPending}
                  >
                    В черновик
                  </Button>
                )}
                <Button size="small" onClick={() => downloadScenarioXlsx(scenarioId)}>
                  Экспорт
                </Button>
                <Popconfirm
                  title="Удалить сценарий?"
                  description="Вместе с раскладками. Отменить нельзя."
                  onConfirm={handleDelete}
                >
                  <Button danger size="small" icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            </div>
          </Card>

          <ScenarioResourceSummary
            scenarioId={scenarioId}
            enabled={!!scenario.team}
            allocations={allocations ?? []}
            employees={resourceBase?.employees}
            pulsedRoles={pulsedRoles}
          />

          {/* Вкладки — на всю ширину над сеткой */}
          <div style={{
            display: 'flex',
            borderBottom: `1px solid ${DARK_THEME.border}`,
            marginBottom: 0,
          }}>
            {(['distribution', 'rules'] as const).map((key) => (
              <div
                key={key}
                onClick={() => setActiveTab(key)}
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  fontSize: 14,
                  borderBottom: activeTab === key ? `2px solid ${DARK_THEME.cyanPrimary}` : '2px solid transparent',
                  marginBottom: -1,
                  color: activeTab === key ? DARK_THEME.cyanPrimary : DARK_THEME.textMuted,
                  transition: 'color .15s',
                  userSelect: 'none' as const,
                }}
              >
                {key === 'distribution' ? 'Распределение' : 'Правила'}
              </div>
            ))}
          </div>

          {/* Двуколоночная сетка */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px', gap: 16, alignItems: 'start' }}>
            {/* Левая колонка — контент активной вкладки */}
            {activeTab === 'distribution' ? (
              <Card
                title="Элементы бэклога"
                styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', flex: 1 } }}
                style={{ display: 'flex', flexDirection: 'column', flex: 1 }}
                loading={allocLoading}
                extra={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                      {isApproved
                        ? 'сценарий утверждён — отметки заблокированы'
                        : 'клик по строке переключает включение'}
                    </span>
                    <Button
                      size="small"
                      type={compact ? 'primary' : 'default'}
                      icon={<CompressOutlined />}
                      onClick={toggleCompact}
                      title={compact ? 'Обычный режим' : 'Компактный режим'}
                    >
                      {compact ? 'Компактный' : 'Обычный'}
                    </Button>
                  </div>
                }
              >
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: GRID,
                    columnGap: GRID_GAP,
                    padding: compact ? '4px 14px' : '8px 14px',
                    borderBottom: `1px solid ${DARK_THEME.border}`,
                    background: DARK_THEME.darkAccent,
                    fontSize: 13,
                    fontWeight: 700,
                    color: DARK_THEME.textPrimary,
                    textTransform: 'uppercase',
                    letterSpacing: 0.6,
                  }}
                >
                  <span title="Включено в сценарий" style={{ textAlign: 'center' }}>
                    <CheckSquareTwoTone
                      className="icon-tick"
                      twoToneColor={DARK_THEME.cyanPrimary}
                      style={{ fontSize: 16 }}
                    />
                  </span>
                  <span title="Приоритет" style={{ textAlign: 'center' }}>
                    <FlagFilled className="flag-wave" style={{ color: DARK_THEME.cyanPrimary, fontSize: 16 }} />
                  </span>
                  <span>Идея</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <UserOutlined className="icon-bob" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
                    Исполнитель
                  </span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <ShopOutlined className="icon-wiggle" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
                    Заказчик
                  </span>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {['АН', 'ПР', 'ТС', 'ОПЭ'].map((l) => (
                      <span key={l} style={{ flex: 1, minWidth: 52, textAlign: 'center' }}>{l}</span>
                    ))}
                  </div>
                  <span style={{ textAlign: 'right', display: 'inline-flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                    <ClockCircleOutlined className="icon-spin-slow" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
                    Всего часов
                  </span>
                </div>
                <div style={{ overflowY: 'auto', flex: 1 }}>
                  {(allocations ?? []).map((a) => {
                    const an = a.estimate_analyst_hours ?? 0;
                    const de = a.estimate_dev_hours ?? 0;
                    const qa = a.estimate_qa_hours ?? 0;
                    const op = a.estimate_opo_hours ?? 0;
                    const total = a.estimate_hours ?? an + de + qa + op;
                    const priorityCyan = a.priority != null && a.priority <= 3;
                    return (
                      <div
                        key={a.id}
                        ref={(el) => {
                          if (el) rowRefs.current.set(a.id, el);
                          else rowRefs.current.delete(a.id);
                        }}
                        className={`backlog-row${flashingIds.has(a.id) ? ' cyan-flash' : ''}`}
                        onClick={() => toggleAllocation(a)}
                        style={{
                          display: 'grid',
                          gridTemplateColumns: GRID,
                          columnGap: GRID_GAP,
                          padding: compact ? '4px 14px' : '12px 14px',
                          fontSize: compact ? 13 : 14,
                          borderBottom: `1px solid ${DARK_THEME.border}`,
                          alignItems: 'center',
                          cursor: isDraft ? 'pointer' : 'default',
                          background: a.included ? 'rgba(0,201,200,0.06)' : 'transparent',
                          opacity: a.included ? 1 : 0.7,
                        }}
                      >
                        <div onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={a.included}
                            disabled={!isDraft}
                            onChange={() => toggleAllocation(a)}
                          />
                        </div>
                        <span
                          style={{
                            width: 24,
                            height: 24,
                            borderRadius: 4,
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            background: priorityCyan ? DARK_THEME.cyanPrimary : DARK_THEME.darkAccent,
                            color: priorityCyan ? '#003a3a' : DARK_THEME.textMuted,
                            fontSize: 11,
                            fontWeight: 700,
                            fontFamily: FONTS.mono,
                          }}
                        >
                          {a.priority ?? '—'}
                        </span>
                        <div>
                          <div style={{ color: DARK_THEME.textPrimary, fontSize: 14, marginBottom: 3 }}>
                            {a.title}
                          </div>
                          {a.source_category === 'quarterly_tasks' && (
                            <span
                              style={{
                                display: 'inline-block',
                                marginTop: 2,
                                fontSize: 11,
                                padding: '1px 6px',
                                borderRadius: 3,
                                background: 'rgba(29,158,117,0.15)',
                                color: '#1D9E75',
                              }}
                            >
                              В работе
                            </span>
                          )}
                          {a.jira_key && (
                            jiraBaseUrl
                              ? (
                                <a
                                  href={`${jiraBaseUrl}/browse/${a.jira_key}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  style={{ fontFamily: FONTS.mono, fontSize: 11, color: DARK_THEME.cyanSecondary }}
                                >
                                  {a.jira_key}
                                </a>
                              )
                              : (
                                <span style={{ fontFamily: FONTS.mono, fontSize: 11, color: DARK_THEME.cyanSecondary }}>
                                  {a.jira_key}
                                </span>
                              )
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
                        {/* Исполнитель */}
                        <div onClick={(e) => e.stopPropagation()}>
                          {!isDraft && !a.assignee_employee_id ? (
                            <span style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
                              {a.assignee_display_name ?? '—'}
                            </span>
                          ) : (
                            <Select
                              size="small"
                              value={a.assignee_employee_id ?? undefined}
                              placeholder={a.assignee_display_name ?? '—'}
                              allowClear
                              disabled={!isDraft}
                              style={{ width: '100%', fontSize: 12 }}
                              options={
                                resourceBase?.employees.map((emp) => ({
                                  label: emp.display_name,
                                  value: emp.employee_id,
                                })) ?? []
                              }
                              onChange={(value: string | undefined) =>
                                patchAssignee.mutate({
                                  scenarioId: scenarioId!,
                                  allocId: a.id,
                                  assigneeEmployeeId: value ?? null,
                                })
                              }
                            />
                          )}
                        </div>
                        {/* Заказчик */}
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
                          <BacklogRoleCell
                            label="АН"
                            hours={an}
                            total={total}
                            color={getRoleColor(roles, 'analyst')}
                          />
                          <BacklogRoleCell
                            label="ПР"
                            hours={de}
                            total={total}
                            color={getRoleColor(roles, 'dev')}
                          />
                          <BacklogRoleCell
                            label="ТС"
                            hours={qa}
                            total={total}
                            color={getRoleColor(roles, 'qa')}
                          />
                          <BacklogRoleCell
                            label="ОПЭ"
                            hours={op}
                            total={total}
                            color={OPO_COLOR}
                          />
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <span style={{ fontFamily: FONTS.mono, fontSize: 14, color: DARK_THEME.textPrimary }}>
                            {Math.round(total)} ч
                          </span>
                          {resourceSummary && resourceSummary.available_for_backlog_total > 0 && (
                            <div style={{ fontSize: 10, color: DARK_THEME.textHint, marginTop: 1 }}>
                              {Math.round((total / resourceSummary.available_for_backlog_total) * 100)}% ресурса
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {(allocations ?? []).length === 0 && !allocLoading && (
                    <div style={{ padding: 24, textAlign: 'center', color: DARK_THEME.textMuted, fontSize: 13 }}>
                      В сценарии нет элементов. Добавьте задачи в бэклог и нажмите
                      «Синк с бэклогом».
                    </div>
                  )}
                </div>
              </Card>
            ) : (
              <Card
                title="Правила обязательных работ"
                styles={{ body: { padding: 14 } }}
                style={{ background: DARK_THEME.cardBg }}
              >
                <ScenarioRulesEditor scenarioId={scenarioId} />
              </Card>
            )}

            {/* Правая колонка — без изменений */}
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <PlanningCapacityPanel
                resourceBase={resourceBase}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
                scenarioId={scenarioId}
                summary={resourceSummary}
              />
              <Card size="small" styles={{ body: { padding: 12 } }}>
                <ExternalQaInput
                  scenarioId={scenarioId}
                  value={scenario.external_qa_hours}
                  disabled={!isDraft}
                />
              </Card>
            </Space>
          </div>
        </Space>
      )}
    </Space>
  );
}
