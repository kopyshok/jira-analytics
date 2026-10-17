import { useMemo, useState } from 'react';
import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import { Alert, Button, Empty, Popconfirm, Segmented, Select, Skeleton, Switch, Tooltip, Typography } from 'antd';
import {
  ArrowDownOutlined, ArrowUpOutlined, CheckOutlined, DeleteOutlined, DownOutlined, PlusOutlined, SwapOutlined,
  UpOutlined, WarningOutlined,
} from '@ant-design/icons';
import '../warm-layout.css';
import './PlanningLayout.css';
import type { PlanningPageState } from '../../../hooks/usePlanningPage';
import BacklogAllocRow from '../../../components/planning/BacklogAllocRow';
import PlanningCapacityPanel from '../../../components/planning/PlanningCapacityPanel';
import ScenarioCreateModal from '../../../components/planning/ScenarioCreateModal';
import ScenarioRulesEditor from '../../../components/planning/ScenarioRulesEditor';
import ExternalQaInput from '../../../components/planning/ExternalQaInput';
import ScenarioResourceSummary from '../../../components/planning/ScenarioResourceSummary';
import ApproveCelebration from '../../../components/planning/ApproveCelebration';
import ScenarioDeficitBadge from '../../../components/planning/ScenarioDeficitBadge';
import ScenarioDiffPanel from '../../../components/planning/ScenarioDiffPanel';
import ScenarioCompareDrawer from '../../../components/planning/ScenarioCompareDrawer';
import ScenarioRevisionHistoryDrawer from '../../../components/planning/ScenarioRevisionHistoryDrawer';
import InvolvementDefaultsDrawer from '../../../components/planning/InvolvementDefaultsDrawer';
import CapacityDriftIndicator from '../../../components/planning/CapacityDriftIndicator';
import SubgroupSectionHeader from '../../../components/planning/SubgroupSectionHeader';
import { TeamSelector } from '../../../components/planning/TeamSelector';
import HoursBreakdownDrawer from '../../../components/hours/HoursBreakdownDrawer';
import EmployeeDrawer from '../../../components/capacity/EmployeeDrawer';
import { downloadScenarioXlsx } from '../../../api/exports';
import { trackAction } from '../../../lib/usage/track';
import { getRoleLabel } from '../../../utils/roles';
import { neighborsTakenTitle } from '../../../utils/multiTeamProgress';
import { nextPersonSort, type PersonSort, type PersonSortKey } from '../../../utils/allocationSort';
import { formatHours, roleHoursTotals, roleShortLabel } from '../../../utils/scenarioView';
import { pluralRu } from '../../../utils/projectsView';

// Колонки таблицы бэклога: ручка, галочка, приоритет, идея, аналитик,
// разработчик, [группа], заказчик, часы ролей, всего, состояние.
const GAP = 6;
const ROW_PADDING = 20;

function backlogGrid(hasSubgroups: boolean, opoOff: boolean) {
  const cols = [
    '18px', '24px', '76px', 'minmax(220px, 1fr)', '116px', '116px',
    ...(hasSubgroups ? ['100px'] : []),
    '108px',
    ...Array.from({ length: opoOff ? 3 : 4 }, () => '40px'),
    '76px', '108px',
  ];
  // Уже этой ширины таблица прокручивается вбок, а не сжимает «Идею».
  const minWidth = cols.reduce((sum, c) => sum + Number(/(\d+)px/.exec(c)?.[1] ?? 0), 0)
    + (cols.length - 1) * GAP + ROW_PADDING;
  return { template: cols.join(' '), minWidth };
}

/** Заголовок колонки с людьми: щелчок — А→Я, Я→А, сброс (только вид на экране). */
function PersonSortHeader({ sortKey, label, sort, onSort }: {
  sortKey: PersonSortKey;
  label: string;
  sort: PersonSort | null;
  onSort: (key: PersonSortKey) => void;
}) {
  const dir = sort?.key === sortKey ? sort.dir : null;
  return (
    <span role="columnheader" aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'}>
      <button
        type="button"
        className={`plc-sort${dir ? ' is-active' : ''}`}
        title="Сортировать: А→Я, Я→А, сброс"
        onClick={() => onSort(sortKey)}
      >
        {label}
        {dir === 'desc' ? <ArrowUpOutlined aria-hidden /> : <ArrowDownOutlined aria-hidden />}
        {dir && <span className="plc-sort-dir">{dir === 'desc' ? 'Я→А' : 'А→Я'}</span>}
      </button>
    </span>
  );
}

/**
 * «Сценарии» в скине «Тёплая» (макет C-scenarios): шапка с выбором сценария,
 * карточка сценария с действиями, свёрнутая сводка ресурса (разворачивается
 * на месте), вкладки и полоса предупреждений, слева таблица идей со своей
 * прокруткой и закреплённой шапкой, справа колонка ресурса команды. Страница
 * помещается в экран. Данные и обработчики — общие с раскладкой Aurora
 * (usePlanningPage).
 */
export default function WarmPlanningLayout({ state }: { state: PlanningPageState }) {
  const {
    navigate, scenarioId, setScenarioId, createOpen, setCreateOpen, activeTab, setActiveTab, celebrate,
    diffOpen, setDiffOpen, compareOpen, setCompareOpen, historyOpen, setHistoryOpen, involvementOpen,
    setInvolvementOpen, ungroupedDrawerId, setUngroupedDrawerId, compact, flashingIds, pulsedRoles, roles,
    jiraBaseUrl, period, breakdown, setBreakdown, scenario, opoOff, allocations, allocLoading, continuation,
    appearanceValue, liftIncluded, updateAppearance, approve, revert, includedIds, personSort, setPersonSort,
    handleDragEnd, quarterInt, resourceBase, resourceSummary, teamAssigneeOptions, isDraft, isApproved,
    roleDemand, deficit, rowStateClass, toggleAllocation, registerRowRef, handlePriorityChange,
    handleAssigneeChange, handleDeveloperChange, hasSubgroups, ungrouped, subgroupOptions, neighborsTakenIds,
    onlyNeighborsTaken, setOnlyNeighborsFor, shownSections, collapsedSections, toggleSection,
    handleSubgroupChange, handleOpenBreakdown, handleApprove, handleRevert, handleDelete, handleTeamChange,
    handleRename, scenarioOptions,
  } = state;
  // Полная сводка ресурса открывается на месте строки — по умолчанию свёрнута, как в макете.
  const [summaryOpen, setSummaryOpen] = useState(false);
  const grid = backlogGrid(hasSubgroups, opoOff);
  const included = useMemo(() => roleHoursTotals(allocations ?? [], opoOff, true), [allocations, opoOff]);
  const onSort = (k: PersonSortKey) => setPersonSort((s) => nextPersonSort(s, k));
  const ready = !!scenarioId && !!scenario && !!scenario.team;

  return (
    <div className="wr-fit plc-page">
      <div className="wr-page-head plc-head">
        <div>
          <div className="wr-eyebrow">Планирование</div>
          <h1 className="wr-h1">Сценарии</h1>
          <p className="wr-subtitle plc-subtitle">Отметьте галочками задачи из бэклога — сформируется план квартала</p>
        </div>
        <div className="wr-row plc-head-actions">
          <div className="wr-field plc-scn-field">
            <label className="wr-field-label" htmlFor="plc-scenario">Сценарий</label>
            <Select
              id="plc-scenario"
              data-tour="planning-scenario-select"
              variant="borderless"
              placeholder="Выберите сценарий"
              value={scenarioId ?? undefined}
              onChange={(v) => setScenarioId(v)}
              options={scenarioOptions}
              allowClear
              onClear={() => setScenarioId(null)}
              popupMatchSelectWidth={false}
              style={{ minWidth: 260, maxWidth: 420 }}
            />
          </div>
          <Tooltip title="Сравнить два сценария">
            <Button icon={<SwapOutlined />} onClick={() => setCompareOpen(true)}>Сравнить</Button>
          </Tooltip>
          <Tooltip title="Вовлечённость и нормированные работы">
            <Button onClick={() => setInvolvementOpen(true)} data-tour="planning-involvement">Вовлечённость</Button>
          </Tooltip>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateOpen(true)}
            data-tour="planning-new-scenario"
          >
            Новый сценарий
          </Button>
        </div>
      </div>

      {!scenarioId && (
        <section className="wr-card plc-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="Сценарии отсутствуют или не выбраны. Нажмите «Новый сценарий», чтобы начать планирование квартала."
          />
        </section>
      )}

      {scenarioId && scenario && !scenario.team && (
        <section className="wr-card plc-team" aria-label="Команда сценария">
          <Alert
            type="info"
            title="Для работы со сценарием выберите команду"
            description="Сценарий привязан к конкретной команде — именно по ней считается ресурс и загрузка."
            showIcon
          />
          <TeamSelector value={scenario.team || null} onChange={handleTeamChange} />
        </section>
      )}

      {ready && (
        <>
          <section className="wr-card plc-scn" aria-label="Выбранный сценарий">
            <div className="wr-row plc-scn-info">
              <span data-tour="planning-scenario-name" className="plc-scn-name">
                <Typography.Text editable={{ onChange: handleRename, tooltip: 'Переименовать', maxLength: 200 }}>
                  {scenario.name}
                </Typography.Text>
              </span>
              <span className="plc-scn-q">{scenario.quarter} {scenario.year}</span>
              <span className={`wr-pill ${isApproved ? 'is-good' : 'is-neutral'}`}>
                {isApproved ? 'Утверждён' : 'Черновик'}
              </span>
              <ScenarioDeficitBadge pill deficit={deficit} />
              {allocations && (
                <span className="plc-scn-count">
                  включено <b>{includedIds.length}</b> из {allocations.length}
                </span>
              )}
            </div>
            <div className="wr-row plc-scn-actions">
              {isDraft ? (
                ungrouped.length > 0 ? (
                  <Tooltip title={`Сначала проставьте группы: ${ungrouped.map((u) => u.display_name).join(', ')}`}>
                    {/* Tooltip не показывается на disabled-кнопках без обёртки. */}
                    <span style={{ display: 'inline-block', cursor: 'not-allowed' }}>
                      <Button type="primary" disabled data-tour="planning-approve">Утвердить</Button>
                    </span>
                  </Tooltip>
                ) : (
                  <Button type="primary" onClick={handleApprove} loading={approve.isPending} data-tour="planning-approve">
                    Утвердить
                  </Button>
                )
              ) : (
                <Button onClick={handleRevert} loading={revert.isPending} data-tour="planning-revert">
                  В черновик
                </Button>
              )}
              {isApproved && (
                <Button
                  onClick={() => navigate(`/resource-planning?scenario_id=${scenario.id}&quarter=${scenario.quarter}&year=${scenario.year}`)}
                  data-tour="planning-diagram"
                >
                  Диаграмма
                </Button>
              )}
              {isDraft && (
                <Tooltip title="Сравнить с последним утверждённым">
                  <Button onClick={() => setDiffOpen(true)}>Diff</Button>
                </Tooltip>
              )}
              <Tooltip title="История ревизий и сравнение снапшотов">
                <Button onClick={() => setHistoryOpen(true)}>История</Button>
              </Tooltip>
              <Tooltip title="При включении задача поднимается в начало списка">
                <label className="plc-switch" data-tour="planning-lift-toggle">
                  <Switch
                    checked={liftIncluded}
                    onChange={(value) =>
                      updateAppearance.mutate({ ...appearanceValue, scenario_lift_included: value })}
                  />
                  поднимать наверх
                </label>
              </Tooltip>
              <Button
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
                <Button className="plc-del" icon={<DeleteOutlined />} aria-label="Удалить сценарий" />
              </Popconfirm>
            </div>
            {isApproved && (
              <div className="plc-scn-drift">
                <CapacityDriftIndicator scenarioId={scenarioId} />
              </div>
            )}
          </section>

          {resourceSummary && resourceSummary.roles.length > 0 && (
            <section className={`wr-card plc-rs${summaryOpen ? ' is-open' : ''}`} aria-label="Сводка ресурса">
              <div className="plc-rs-row">
                <div className="plc-rs-info">
                  <b className="plc-rs-title">Сводка ресурса</b>
                  <span>
                    На бэклог <b>{formatHours(Math.round(resourceSummary.available_for_backlog_total))} ч</b>
                  </span>
                  <span className="plc-rs-rest">
                    Остаток по ролям
                    {resourceSummary.roles.map((role) => {
                      const avail = resourceSummary.available_for_backlog_by_role[role] ?? 0;
                      const used = roleDemand[role] ?? 0;
                      const rest = Math.round(avail - used);
                      return (
                        <Tooltip
                          key={role}
                          title={`${getRoleLabel(roles, role)}: на бэклог ${formatHours(Math.round(avail))} ч, в плане ${formatHours(Math.round(used))} ч`}
                        >
                          <span
                            tabIndex={0}
                            className={`wr-pill is-sm ${rest < 0 ? 'is-bad' : 'is-good'}${pulsedRoles.has(role) ? ' role-pulse' : ''}`}
                          >
                            {roleShortLabel(role, getRoleLabel(roles, role))} {formatHours(rest)} ч
                          </span>
                        </Tooltip>
                      );
                    })}
                  </span>
                </div>
                <button
                  type="button"
                  className="plc-rs-toggle"
                  aria-expanded={summaryOpen}
                  onClick={() => setSummaryOpen((v) => !v)}
                >
                  {summaryOpen ? <UpOutlined aria-hidden /> : <DownOutlined aria-hidden />}
                  {summaryOpen ? 'Свернуть' : 'Развернуть'}
                </button>
              </div>
              {summaryOpen && (
                <div className="plc-rs-body">
                  <ScenarioResourceSummary
                    docked
                    scenarioId={scenarioId}
                    enabled={!!scenario.team}
                    allocations={allocations ?? []}
                    employees={resourceBase?.employees}
                    pulsedRoles={pulsedRoles}
                  />
                </div>
              )}
            </section>
          )}

          <div className="plc-tabs-row">
            <Segmented
              className="plc-tabs"
              value={activeTab}
              onChange={(v) => setActiveTab(v as 'distribution' | 'rules')}
              options={[
                { value: 'distribution', label: <span data-tour="planning-tab-distribution">Распределение</span> },
                { value: 'rules', label: <span data-tour="planning-tab-rules">Правила</span> },
              ]}
            />
            {activeTab === 'distribution' && neighborsTakenIds.size > 0 && (
              <div role="status" className="plc-strip is-warn">
                <span className="plc-strip-text">
                  <WarningOutlined aria-hidden />
                  {neighborsTakenTitle(neighborsTakenIds.size)}
                </span>
                <label className="plc-switch">
                  <Switch
                    checked={onlyNeighborsTaken}
                    onChange={(on) => setOnlyNeighborsFor(on ? scenarioId : null)}
                  />
                  Показать только их
                </label>
              </div>
            )}
            {activeTab === 'distribution' && neighborsTakenIds.size === 0 && (
              <div role="status" className="plc-strip is-calm">
                <span className="plc-strip-text">
                  <CheckOutlined aria-hidden />
                  Нет задач, которые соседние команды взяли, а у вас они не включены
                </span>
              </div>
            )}
            {isDraft && ungrouped.length > 0 && (
              <div role="alert" className="plc-strip is-bad">
                <span className="plc-strip-text">
                  <WarningOutlined aria-hidden />
                  Без группы: {ungrouped.length} чел. — сценарий нельзя утвердить:
                  {ungrouped.map((u, i) => (
                    <span key={u.employee_id}>
                      {i > 0 && ','}
                      {' '}
                      <button type="button" className="wr-link" onClick={() => setUngroupedDrawerId(u.employee_id)}>
                        {u.display_name}
                      </button>
                    </span>
                  ))}
                </span>
                <button type="button" className="wr-link" onClick={() => navigate('/capacity')}>
                  Открыть «Ресурсы»
                </button>
              </div>
            )}
          </div>

          <div className="plc-body">
            {activeTab === 'distribution' ? (
              <section className="wr-card plc-backlog" aria-label="Элементы бэклога">
                <div className="plc-backlog-head">
                  <div className="plc-backlog-title">
                    <h2 className="rpc-card-title">Элементы бэклога</h2>
                    <span className="wr-muted">
                      {isApproved
                        ? 'сценарий утверждён — отметки заблокированы'
                        : 'клик по строке переключает включение'}
                    </span>
                  </div>
                  {allocations && allocations.length > 0 && (
                    <Tooltip title="Часы включённых идей по ролям">
                      <div className="plc-backlog-sums" tabIndex={0}>
                        <b>
                          {allocations.length} {pluralRu(allocations.length, ['идея', 'идеи', 'идей'])}
                          {' · '}включено {included.included}
                        </b>
                        <span className="plc-sum">АН <b>{formatHours(Math.round(included.analyst))}</b></span>
                        <span className="plc-sum">ПР <b>{formatHours(Math.round(included.dev))}</b></span>
                        <span className="plc-sum">ТС <b>{formatHours(Math.round(included.qa))}</b></span>
                        {!opoOff && <span className="plc-sum">ОПЭ <b>{formatHours(Math.round(included.opo))}</b></span>}
                        <span className="plc-sum is-total">{formatHours(Math.round(included.total))} ч</span>
                      </div>
                    </Tooltip>
                  )}
                </div>
                <div className="plc-table-scroll">
                  <div className="plc-table" style={{ minWidth: grid.minWidth }}>
                    <div
                      className="plc-thead"
                      role="row"
                      style={{ gridTemplateColumns: grid.template, columnGap: GAP }}
                    >
                      <span aria-hidden />
                      <span className="is-center" title="Включено в сценарий">Вкл</span>
                      <span className="is-center">Приоритет</span>
                      <span>Идея</span>
                      <PersonSortHeader sortKey="analyst" label="Аналитик" sort={personSort} onSort={onSort} />
                      <PersonSortHeader sortKey="developer" label="Разработчик" sort={personSort} onSort={onSort} />
                      {hasSubgroups && <span>Группа</span>}
                      <span>Заказчик</span>
                      {(opoOff ? ['АН', 'ПР', 'ТС'] : ['АН', 'ПР', 'ТС', 'ОПЭ']).map((l) => (
                        <span key={l} className="is-num">{l}</span>
                      ))}
                      <span className="is-num">Всего часов</span>
                      <span>Состояние</span>
                    </div>
                    {allocLoading ? (
                      <div className="plc-table-loading"><Skeleton active paragraph={{ rows: 6 }} /></div>
                    ) : (
                      <DndContext
                        collisionDetection={closestCenter}
                        modifiers={[restrictToVerticalAxis]}
                        onDragEnd={handleDragEnd}
                      >
                        {shownSections.map((section) => {
                          const collapsed = section.id !== null && collapsedSections.has(section.id);
                          return (
                            <div key={section.id ?? '__all__'}>
                              {section.id !== null && (
                                <SubgroupSectionHeader
                                  flat
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
                                  {section.items.map((a) => (
                                    <BacklogAllocRow
                                      key={a.id}
                                      flat
                                      alloc={a}
                                      scenarioId={scenarioId}
                                      scenarioStatus={(scenario.status ?? 'draft') as 'draft' | 'approved'}
                                      isDraft={isDraft}
                                      dragLocked={personSort !== null}
                                      compact={compact}
                                      flashing={flashingIds.has(a.id)}
                                      rowStateClass={rowStateClass(a)}
                                      gridTemplate={grid.template}
                                      gridGap={GAP}
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
                                </SortableContext>
                              )}
                            </div>
                          );
                        })}
                      </DndContext>
                    )}
                    {(allocations ?? []).length === 0 && !allocLoading && (
                      <div className="plc-table-empty">
                        В сценарии нет элементов. Добавьте задачи в бэклог — они появятся автоматически.
                      </div>
                    )}
                  </div>
                </div>
              </section>
            ) : (
              <section className="wr-card plc-rules" data-tour="planning-rules-card" aria-label="Правила обязательных работ">
                <h2 className="rpc-card-title">Правила обязательных работ</h2>
                <div className="plc-rules-body">
                  <ScenarioRulesEditor scenarioId={scenarioId} />
                </div>
              </section>
            )}

            <aside className="plc-side" aria-label="Ресурс команды">
              <PlanningCapacityPanel
                compact
                resourceBase={resourceBase}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
                scenarioId={scenarioId}
                summary={resourceSummary}
              />
              <section className="wr-card plc-qa-card">
                <ExternalQaInput
                  compact
                  scenarioId={scenarioId}
                  value={scenario.external_qa_hours}
                  disabled={!isDraft}
                />
              </section>
            </aside>
          </div>
        </>
      )}

      <ScenarioCreateModal
        open={createOpen}
        onClose={(createdId) => {
          setCreateOpen(false);
          if (createdId) setScenarioId(createdId);
        }}
      />
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
      <EmployeeDrawer employeeId={ungroupedDrawerId} onClose={() => setUngroupedDrawerId(null)} />
      <HoursBreakdownDrawer
        open={breakdown.open}
        onClose={() => setBreakdown((b) => ({ ...b, open: false }))}
        issueId={breakdown.issueId}
        issueKey={breakdown.issueKey}
        year={period.year}
        quarter={period.quarter}
      />
    </div>
  );
}
