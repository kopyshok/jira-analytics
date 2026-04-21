import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import {
  Alert, App, Badge, Button, Card, Checkbox, Popconfirm, Select, Space, Tabs, Tag, Tooltip,
} from 'antd';
import {
  CheckCircleOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined, RollbackOutlined,
} from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import PlanningCapacityPanel from '../components/planning/PlanningCapacityPanel';
import ScenarioCreateModal from '../components/planning/ScenarioCreateModal';
import ScenarioRulesEditor from '../components/planning/ScenarioRulesEditor';
import ExternalQaInput from '../components/planning/ExternalQaInput';
import ScenarioResourceSummary from '../components/planning/ScenarioResourceSummary';
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
  useUpdateScenario,
} from '../hooks/usePlanning';
import { TeamSelector } from '../components/planning/TeamSelector';
import { downloadScenarioXlsx } from '../api/exports';
import { DARK_THEME, FONTS } from '../utils/constants';
import { useRoles } from '../hooks/useRoles';
import { useJiraSettings } from '../hooks/useSettings';
import { getRoleColor } from '../utils/roles';
import { OPO_COLOR } from '../utils/opo';
import type { AllocationResponse, BacklogImpactRisk } from '../types/api';

const IMPACT_COLORS: Record<BacklogImpactRisk, string> = { low: 'default', medium: 'blue', high: 'cyan' };
const IMPACT_LABELS: Record<BacklogImpactRisk, string> = { low: 'низкий', medium: 'средний', high: 'высокий' };
const RISK_COLORS: Record<BacklogImpactRisk, string> = { low: 'green', medium: 'default', high: 'warning' };
const RISK_LABELS: Record<BacklogImpactRisk, string> = { low: 'низкий', medium: 'средний', high: 'высокий' };

const GRID = '40px 60px 1fr 200px 75px 100px 95px';

export default function PlanningPage() {
  const { notification } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);

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
  const updateScenario = useUpdateScenario();
  const deleteScenario = useDeleteScenario();
  const approve = useApproveScenario();
  const revert = useRevertScenario();
  const syncBacklog = useSyncScenarioBacklog();

  // Запоминаем id, который сейчас удаляется, — иначе авто-выбор ниже успеет
  // снова взять его из стейл-кэша списка между `setScenarioId(null)` и
  // refetch'ем, и лечит 404 на useScenario/useScenarioAllocations.
  const deletingIdRef = useRef<string | null>(null);

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

  const isDraft = scenario?.status === 'draft';
  const isApproved = scenario?.status === 'approved';

  const toggleAllocation = (alloc: AllocationResponse) => {
    if (!scenarioId || !isDraft) return;
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
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
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

          <ScenarioResourceSummary scenarioId={scenarioId} enabled={!!scenario.team} />

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px', gap: 16, alignItems: 'start' }}>
            <Tabs
              defaultActiveKey="distribution"
              items={[
                {
                  key: 'distribution',
                  label: 'Распределение',
                  children: (
                    <Card
                      title="Элементы бэклога"
                      styles={{ body: { padding: 0 } }}
                      loading={allocLoading}
                      extra={
                        <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                          {isApproved
                            ? 'сценарий утверждён — отметки заблокированы'
                            : 'клик по строке переключает включение'}
                        </span>
                      }
                    >
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: GRID,
                          padding: '8px 14px',
                          borderBottom: `1px solid ${DARK_THEME.border}`,
                          background: DARK_THEME.darkAccent,
                          fontSize: 10,
                          color: DARK_THEME.textMuted,
                          textTransform: 'uppercase',
                          letterSpacing: 0.6,
                        }}
                      >
                        <span>✓</span>
                        <span>Прио</span>
                        <span>Идея</span>
                        <span>АН / ПР / ТС / ОПЭ</span>
                        <span style={{ textAlign: 'right' }}>Всего</span>
                        <span>Влияние</span>
                        <span>Риск</span>
                      </div>
                      <div style={{ maxHeight: 640, overflowY: 'auto' }}>
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
                              onClick={() => toggleAllocation(a)}
                              style={{
                                display: 'grid',
                                gridTemplateColumns: GRID,
                                padding: '12px 14px',
                                borderBottom: `1px solid ${DARK_THEME.border}`,
                                alignItems: 'center',
                                cursor: isDraft ? 'pointer' : 'default',
                                background: a.included ? 'rgba(0,201,200,0.06)' : 'transparent',
                                opacity: a.included ? 1 : 0.7,
                                transition: 'background .15s',
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
                                <div style={{ color: DARK_THEME.textPrimary, fontSize: 13, marginBottom: 3 }}>
                                  {a.title}
                                </div>
                                {a.jira_key && (
                                  jiraBaseUrl
                                    ? (
                                      <a
                                        href={`${jiraBaseUrl}/browse/${a.jira_key}`}
                                        target="_blank"
                                        rel="noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                        style={{ fontFamily: FONTS.mono, fontSize: 10, color: DARK_THEME.cyanSecondary }}
                                      >
                                        {a.jira_key}
                                      </a>
                                    )
                                    : (
                                      <span style={{ fontFamily: FONTS.mono, fontSize: 10, color: DARK_THEME.cyanSecondary }}>
                                        {a.jira_key}
                                      </span>
                                    )
                                )}
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <div
                                  style={{
                                    display: 'flex',
                                    height: 16,
                                    width: 120,
                                    borderRadius: 3,
                                    overflow: 'hidden',
                                    background: DARK_THEME.darkAccent,
                                  }}
                                >
                                  {total > 0 && an > 0 && (
                                    <div title={`Аналитик: ${an} ч`} style={{ width: `${(an / total) * 100}%`, background: getRoleColor(roles, 'analyst') }} />
                                  )}
                                  {total > 0 && de > 0 && (
                                    <div title={`Программист: ${de} ч`} style={{ width: `${(de / total) * 100}%`, background: getRoleColor(roles, 'dev') }} />
                                  )}
                                  {total > 0 && qa > 0 && (
                                    <div title={`Тестировщик: ${qa} ч`} style={{ width: `${(qa / total) * 100}%`, background: getRoleColor(roles, 'qa') }} />
                                  )}
                                  {total > 0 && op > 0 && (
                                    <div title={`ОПЭ: ${op} ч`} style={{ width: `${(op / total) * 100}%`, background: OPO_COLOR }} />
                                  )}
                                </div>
                                <div style={{ fontFamily: FONTS.mono, fontSize: 10, color: DARK_THEME.textHint, whiteSpace: 'nowrap' }}>
                                  {an}/{de}/{qa}/{op}
                                </div>
                              </div>
                              <span style={{ textAlign: 'right', fontFamily: FONTS.mono, fontSize: 13, color: DARK_THEME.textPrimary }}>
                                {Math.round(total)} ч
                              </span>
                              <div>
                                {a.impact ? (
                                  <Tag color={IMPACT_COLORS[a.impact]}>{IMPACT_LABELS[a.impact]}</Tag>
                                ) : (
                                  <span style={{ color: DARK_THEME.textDim, fontSize: 11 }}>—</span>
                                )}
                              </div>
                              <div>
                                {a.risk ? (
                                  <Tag color={RISK_COLORS[a.risk]}>{RISK_LABELS[a.risk]}</Tag>
                                ) : (
                                  <span style={{ color: DARK_THEME.textDim, fontSize: 11 }}>—</span>
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
                  ),
                },
                {
                  key: 'rules',
                  label: 'Правила',
                  children: (
                    <Card
                      title="Правила обязательных работ"
                      styles={{ body: { padding: 14 } }}
                      style={{ background: DARK_THEME.cardBg }}
                    >
                      <ScenarioRulesEditor scenarioId={scenarioId} />
                    </Card>
                  ),
                },
              ]}
            />

            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <PlanningCapacityPanel
                resourceBase={resourceBase}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
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
