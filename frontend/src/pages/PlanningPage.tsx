import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import { useState } from 'react';
import {
  Alert, Badge, Button, Card, Popconfirm, Select, Space, Switch, Tooltip, Typography,
} from 'antd';
import {
  BarChartOutlined, CheckCircleOutlined, CheckSquareTwoTone, ClockCircleOutlined,
  CodeOutlined, DeleteOutlined, DiffOutlined, FlagFilled, HistoryOutlined,
  PlusOutlined, RollbackOutlined, ShopOutlined, SwapOutlined, UserOutlined,
} from '@ant-design/icons';
import BacklogAllocRow from '../components/planning/BacklogAllocRow';
import PageHeader from '../components/shared/PageHeader';
import PlanningCapacityPanel from '../components/planning/PlanningCapacityPanel';
import ScenarioCreateModal from '../components/planning/ScenarioCreateModal';
import ScenarioRulesEditor from '../components/planning/ScenarioRulesEditor';
import ExternalQaInput from '../components/planning/ExternalQaInput';
import ScenarioResourceSummary from '../components/planning/ScenarioResourceSummary';
import ApproveCelebration from '../components/planning/ApproveCelebration';
import ScenarioDeficitBadge from '../components/planning/ScenarioDeficitBadge';
import ScenarioDiffPanel from '../components/planning/ScenarioDiffPanel';
import ScenarioCompareDrawer from '../components/planning/ScenarioCompareDrawer';
import ScenarioRevisionHistoryDrawer from '../components/planning/ScenarioRevisionHistoryDrawer';
import InvolvementDefaultsDrawer from '../components/planning/InvolvementDefaultsDrawer';
import HoursBreakdownDrawer from '../components/hours/HoursBreakdownDrawer';
import EmployeeDrawer from '../components/capacity/EmployeeDrawer';
import SubgroupSectionHeader from '../components/planning/SubgroupSectionHeader';
import NeighborsTakenBanner from '../components/planning/NeighborsTakenBanner';
import SortableHeader from '../components/planning/PersonSortHeader';
import CapacityDriftIndicator from '../components/planning/CapacityDriftIndicator';
import { TeamSelector } from '../components/planning/TeamSelector';
import { useStickyViewportHeight } from '../hooks/useStickyViewportHeight';
import { downloadScenarioXlsx } from '../api/exports';
import { trackAction } from '../lib/usage/track';
import { DARK_THEME, FONTS } from '../utils/constants';
import { nextPersonSort } from '../utils/allocationSort';
import { useSkin } from '../contexts/ThemeContext';
import {
  GRID, GRID_GAP, GRID_WITH_SUBGROUP, gridMinWidth, usePlanningPage, type PlanningPageState,
} from '../hooks/usePlanningPage';
import PlanningZonesLayout from '../skins/zones/pages/PlanningLayout';

function PlanningAuroraLayout({ pl }: { pl: PlanningPageState }) {
  const {
    navigate, scenarioId, setScenarioId, createOpen, setCreateOpen,
    activeTab, setActiveTab, celebrate, diffOpen, setDiffOpen, compareOpen,
    setCompareOpen, historyOpen, setHistoryOpen, involvementOpen, setInvolvementOpen, ungroupedDrawerId,
    setUngroupedDrawerId, compact, flashingIds, pulsedRoles, roles, jiraBaseUrl,
    period, breakdown, setBreakdown, scenario, opoOff,
    allocations, allocLoading, continuation, appearanceValue, liftIncluded, updateAppearance,
    approve, revert, includedIds, personSort, setPersonSort,
    handleDragEnd, quarterInt, resourceBase, resourceSummary, teamAssigneeOptions, isDraft,
    isApproved, deficit, rowStateClass, toggleAllocation, registerRowRef, handlePriorityChange,
    handleAssigneeChange, handleDeveloperChange, hasSubgroups, ungrouped, subgroupOptions,
    neighborsTakenIds, onlyNeighborsTaken, setOnlyNeighborsFor, shownSections, collapsedSections,
    toggleSection, handleSubgroupChange, handleOpenBreakdown, handleApprove, handleRevert, handleDelete,
    handleTeamChange, handleRename, scenarioOptions,
  } = pl;
  // Правая колонка листается сама по себе — иначе её низ достижим только
  // после прокрутки всего бэклога. 72 = отступ sticky сверху + воздух снизу.
  const [rightColumnEl, setRightColumnEl] = useState<HTMLDivElement | null>(null);
  const rightColumnHeight = useStickyViewportHeight(rightColumnEl, 72);

  return (
    <Space orientation="vertical" size={12} style={{ width: '100%' }}>
      <div>
      <PageHeader
        eyebrow="Планирование"
        title="Сценарии"
        subtitle="Отметьте галочками задачи из бэклога — сформируется план квартала"
        actions={
          <Space>
            <Select
              data-tour="planning-scenario-select"
              style={{ minWidth: 320 }}
              placeholder="Выберите сценарий"
              value={scenarioId ?? undefined}
              onChange={(v) => setScenarioId(v)}
              options={scenarioOptions}
              allowClear
              onClear={() => setScenarioId(null)}
            />
            <Tooltip title="Сравнить два сценария">
              <Button icon={<SwapOutlined />} onClick={() => setCompareOpen(true)}>
                Сравнить
              </Button>
            </Tooltip>
            <Tooltip title="Вовлечённость и нормированные работы">
              <Button onClick={() => setInvolvementOpen(true)} data-tour="planning-involvement">
                Вовлечённость
              </Button>
            </Tooltip>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)} data-tour="planning-new-scenario">
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
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <Alert
              type="info"
              title="Для работы со сценарием выберите команду"
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
        // Намеренно plain `<div>`, не AntD `<Space>`: Space оборачивает каждого
        // ребёнка в `.ant-space-item`, который становится containing-block'ом
        // для `position: sticky` на ScenarioResourceSummary — и поскольку он
        // высотой ровно равен таблице, прилипать некуда. Тут все дочерние
        // элементы лежат прямо в flex-контейнере, и sticky упирается в его
        // полную высоту страницы.
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, width: '100%' }}>
          <Card
            styles={{ body: { padding: '14px 18px' } }}
            style={{ background: DARK_THEME.cardBg }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span data-tour="planning-scenario-name">
                <Typography.Text
                  editable={{
                    onChange: handleRename,
                    tooltip: 'Переименовать',
                    maxLength: 200,
                  }}
                  style={{ fontSize: 18, fontWeight: 600, color: DARK_THEME.textPrimary, margin: 0 }}
                >
                  {scenario.name}
                </Typography.Text>
                </span>
                <span style={{ color: DARK_THEME.textMuted, fontFamily: FONTS.mono, fontSize: 13 }}>
                  {scenario.quarter} {scenario.year}
                </span>
                <Badge
                  status={isApproved ? 'success' : 'processing'}
                  text={isApproved ? 'Утверждён' : 'Черновик'}
                />
                <ScenarioDeficitBadge deficit={deficit} />
                {allocations && (
                  <span style={{ color: DARK_THEME.textHint, fontSize: 12 }}>
                    включено {includedIds.length} из {allocations.length}
                  </span>
                )}
              </div>
              <Space>
                {isDraft ? (
                  ungrouped.length > 0 ? (
                    <Tooltip title={`Сначала проставьте группы: ${ungrouped.map((u) => u.display_name).join(', ')}`}>
                      {/* Tooltip не показывается на disabled-кнопках без обёртки. */}
                      <span style={{ display: 'inline-block', cursor: 'not-allowed' }}>
                        <Button
                          type="primary"
                          icon={<CheckCircleOutlined />}
                          size="small"
                          disabled
                          data-tour="planning-approve"
                        >
                          Утвердить
                        </Button>
                      </span>
                    </Tooltip>
                  ) : (
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      size="small"
                      onClick={handleApprove}
                      loading={approve.isPending}
                      data-tour="planning-approve"
                    >
                      Утвердить
                    </Button>
                  )
                ) : (
                  <Button
                    icon={<RollbackOutlined />}
                    size="small"
                    onClick={handleRevert}
                    loading={revert.isPending}
                    data-tour="planning-revert"
                  >
                    В черновик
                  </Button>
                )}
                {isApproved && scenario && (
                  <Button
                    size="small"
                    icon={<BarChartOutlined />}
                    onClick={() => navigate(`/resource-planning?scenario_id=${scenario.id}&quarter=${scenario.quarter}&year=${scenario.year}`)}
                    data-tour="planning-diagram"
                  >
                    Диаграмма
                  </Button>
                )}
                {isDraft && (
                  <Tooltip title="Сравнить с последним утверждённым">
                    <Button
                      icon={<DiffOutlined />}
                      size="small"
                      onClick={() => setDiffOpen(true)}
                    >
                      Diff
                    </Button>
                  </Tooltip>
                )}
                <Tooltip title="История ревизий и сравнение снапшотов">
                  <Button
                    icon={<HistoryOutlined />}
                    size="small"
                    onClick={() => setHistoryOpen(true)}
                  >
                    История
                  </Button>
                </Tooltip>
                <Tooltip title="При включении задача поднимается в начало списка">
                  <Space size={6} data-tour="planning-lift-toggle">
                    <Switch
                      size="small"
                      checked={liftIncluded}
                      onChange={(value) =>
                        updateAppearance.mutate({
                          ...appearanceValue,
                          scenario_lift_included: value,
                        })}
                    />
                    <span style={{ color: DARK_THEME.textHint, fontSize: 12 }}>
                      поднимать наверх
                    </span>
                  </Space>
                </Tooltip>
                <Button
                  size="small"
                  onClick={() => {
                    downloadScenarioXlsx(scenarioId);
                    trackAction('scenario_xlsx_exported', scenarioId);
                  }}
                >
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
            {isApproved && scenarioId && (
              <CapacityDriftIndicator scenarioId={scenarioId} />
            )}
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
                data-tour={`planning-tab-${key}`}
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

          {isDraft && ungrouped.length > 0 && (
            <Alert
              type="error"
              showIcon
              title={`Без группы: ${ungrouped.length} чел. — сценарий нельзя утвердить`}
              description={
                <>
                  {ungrouped.map((u, i) => (
                    <span key={u.employee_id}>
                      {i > 0 && ', '}
                      <a onClick={() => setUngroupedDrawerId(u.employee_id)}>{u.display_name}</a>
                    </span>
                  ))}
                  {' — '}
                  <a onClick={() => navigate('/capacity')}>Открыть «Ресурсы»</a>
                </>
              }
            />
          )}

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
                  <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                    {isApproved
                      ? 'сценарий утверждён — отметки заблокированы'
                      : 'клик по строке переключает включение'}
                  </span>
                }
              >
                {neighborsTakenIds.size > 0 && (
                  <NeighborsTakenBanner
                    count={neighborsTakenIds.size}
                    onlyThem={onlyNeighborsTaken}
                    onOnlyThemChange={(on) => setOnlyNeighborsFor(on ? scenarioId : null)}
                  />
                )}
                <div style={{ overflowX: 'auto' }}>
                <div style={{ minWidth: gridMinWidth(hasSubgroups ? GRID_WITH_SUBGROUP : GRID) }}>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: hasSubgroups ? GRID_WITH_SUBGROUP : GRID,
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
                  <span aria-hidden style={{ textAlign: 'center' }} />
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
                  <SortableHeader
                    sortKey="analyst"
                    sort={personSort}
                    onSort={(k) => setPersonSort((s) => nextPersonSort(s, k))}
                  >
                    <UserOutlined className="icon-bob" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
                    Аналитик
                  </SortableHeader>
                  <SortableHeader
                    sortKey="developer"
                    sort={personSort}
                    onSort={(k) => setPersonSort((s) => nextPersonSort(s, k))}
                  >
                    <CodeOutlined style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
                    Разработчик
                  </SortableHeader>
                  {hasSubgroups && <span>Группа</span>}
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <ShopOutlined className="icon-wiggle" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
                    Заказчик
                  </span>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {(opoOff ? ['АН', 'ПР', 'ТС'] : ['АН', 'ПР', 'ТС', 'ОПЭ']).map((l) => (
                      <span key={l} style={{ flex: 1, minWidth: 52, textAlign: 'center' }}>{l}</span>
                    ))}
                  </div>
                  <span style={{ textAlign: 'right', display: 'inline-flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                    <ClockCircleOutlined className="icon-spin-slow" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
                    Всего часов
                  </span>
                </div>
                <DndContext
                  collisionDetection={closestCenter}
                  modifiers={[restrictToVerticalAxis]}
                  onDragEnd={handleDragEnd}
                >
                  <div>
                  {shownSections.map((section) => {
                    const collapsed = section.id !== null && collapsedSections.has(section.id);
                    return (
                      <div key={section.id ?? '__all__'}>
                        {section.id !== null && (
                          <SubgroupSectionHeader
                            name={section.name}
                            items={section.items}
                            collapsed={collapsed}
                            roles={roles}
                            opoOff={opoOff}
                            onToggle={() => toggleSection(section.id!)}
                          />
                        )}
                        {!collapsed && (
                          <SortableContext
                            items={section.items.map((a) => a.id)}
                            strategy={verticalListSortingStrategy}
                          >
                            <div>
                              {section.items.map((a) => (
                                <BacklogAllocRow
                                  key={a.id}
                                  alloc={a}
                                  scenarioId={scenarioId!}
                                  scenarioStatus={(scenario?.status ?? 'draft') as 'draft' | 'approved'}
                                  isDraft={isDraft}
                                  dragLocked={personSort !== null}
                                  compact={compact}
                                  flashing={flashingIds.has(a.id)}
                                  rowStateClass={rowStateClass(a)}
                                  gridTemplate={hasSubgroups ? GRID_WITH_SUBGROUP : GRID}
                                  gridGap={GRID_GAP}
                                  continuationInfo={continuation?.info_by_allocation_id?.[a.id]}
                                  teamAssigneeOptions={teamAssigneeOptions}
                                  subgroupOptions={hasSubgroups ? subgroupOptions : undefined}
                                  roles={roles}
                                  opoOff={opoOff}
                                  jiraBaseUrl={jiraBaseUrl}
                                  resourceTotalForBacklog={resourceSummary?.available_for_backlog_total ?? 0}
                                  registerRef={registerRowRef}
                                  onToggle={toggleAllocation}
                                  onPriorityChange={handlePriorityChange}
                                  onAssigneeChange={handleAssigneeChange}
                                  onDeveloperChange={handleDeveloperChange}
                                  onSubgroupChange={handleSubgroupChange}
                                  onOpenBreakdown={handleOpenBreakdown}
                                />
                              ))}
                            </div>
                          </SortableContext>
                        )}
                      </div>
                    );
                  })}
                  {(allocations ?? []).length === 0 && !allocLoading && (
                    <div style={{ padding: 24, textAlign: 'center', color: DARK_THEME.textMuted, fontSize: 13 }}>
                      В сценарии нет элементов. Добавьте задачи в бэклог — они появятся автоматически.
                    </div>
                  )}
                  </div>
                </DndContext>
                </div>
                </div>
              </Card>
            ) : (
              <Card
                data-tour="planning-rules-card"
                title="Правила обязательных работ"
                styles={{ body: { padding: 14 } }}
                style={{ background: DARK_THEME.cardBg }}
              >
                <ScenarioRulesEditor scenarioId={scenarioId} />
              </Card>
            )}

            {/* Правая колонка — sticky сверху, со своей прокруткой: секции по
                группам сделали блок выше экрана, и без этого до его низа
                приходилось прокручивать весь бэклог. Высоту берём от реального
                контейнера прокрутки — в Aurora страница листается внутри
                собственного вьюпорта, и 100vh там обрезал нижнюю карточку. */}
            <div
              ref={setRightColumnEl}
              style={{
                position: 'sticky',
                top: 56,
                alignSelf: 'start',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                maxHeight: rightColumnHeight,
                overflowY: 'auto',
                paddingRight: 4,
              }}
            >
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
            </div>
          </div>
        </div>
      )}
      {scenario && allocations && isDraft && (
        <ScenarioDiffPanel
          open={diffOpen}
          onClose={() => setDiffOpen(false)}
          draftScenario={scenario}
          draftAllocations={allocations}
        />
      )}
      <ScenarioCompareDrawer
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        initialScenarioId={scenarioId ?? undefined}
      />
      <ScenarioRevisionHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        scenarioId={scenarioId}
      />
      <InvolvementDefaultsDrawer
        open={involvementOpen}
        onClose={() => setInvolvementOpen(false)}
        team={scenario?.team ?? null}
        scenarioId={scenarioId}
      />
      <ApproveCelebration visible={celebrate} />
      <EmployeeDrawer
        employeeId={ungroupedDrawerId}
        onClose={() => setUngroupedDrawerId(null)}
      />
      <HoursBreakdownDrawer
        open={breakdown.open}
        onClose={() => setBreakdown((b) => ({ ...b, open: false }))}
        issueId={breakdown.issueId}
        issueKey={breakdown.issueKey}
        year={period.year}
        quarter={period.quarter}
      />
    </Space>
  );
}

export default function PlanningPage() {
  const pl = usePlanningPage();
  const skin = useSkin();
  if (skin === 'zones') return <PlanningZonesLayout pl={pl} />;
  return <PlanningAuroraLayout pl={pl} />;
}
