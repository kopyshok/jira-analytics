import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import {
  Alert, Button, Popconfirm, Select, Spin, Switch, Tooltip, Typography,
} from 'antd';
import {
  ArrowLeftRight, BarChart3, CheckCircle2, Download, GitCompare, History, Plus, Trash2, Undo2, Users,
} from 'lucide-react';
import './planning.css';
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
import HoursBreakdownDrawer from '../../../components/hours/HoursBreakdownDrawer';
import EmployeeDrawer from '../../../components/capacity/EmployeeDrawer';
import SubgroupSectionHeader from '../../../components/planning/SubgroupSectionHeader';
import NeighborsTakenBanner from '../../../components/planning/NeighborsTakenBanner';
import SortableHeader from '../../../components/planning/PersonSortHeader';
import CapacityDriftIndicator from '../../../components/planning/CapacityDriftIndicator';
import { TeamSelector } from '../../../components/planning/TeamSelector';
import { downloadScenarioXlsx } from '../../../api/exports';
import { trackAction } from '../../../lib/usage/track';
import { nextPersonSort } from '../../../utils/allocationSort';
import { GRID_GAP, gridMinWidth, type PlanningPageState } from '../../../hooks/usePlanningPage';
import ZonesBand, { BandField, BandTabs } from '../ZonesBand';

const SUBTITLE = 'Отметьте галочками задачи из бэклога — сформируется план квартала';
// Плотная сетка таблицы скина: часы ролей — числами, «Идея» забирает остаток.
const GRID_Z = '20px 44px 64px minmax(200px, 1fr) 118px 118px 130px 192px 76px';
const GRID_Z_SUB = '20px 44px 64px minmax(200px, 1fr) 118px 118px 104px 130px 192px 76px';

/**
 * «Сценарии» в скине «Цветовые зоны»: выбор сценария, сравнение, вовлечённость
 * и вкладки — в полосе зоны; в теле карточка сценария, свёрнутая сводка
 * ресурса, таблица бэклога (листается внутри) и ресурс команды справа.
 */
export default function PlanningZonesLayout({ pl }: { pl: PlanningPageState }) {
  const {
    navigate, scenarioId, setScenarioId, createOpen, setCreateOpen, activeTab, setActiveTab,
    celebrate, diffOpen, setDiffOpen, compareOpen, setCompareOpen, historyOpen, setHistoryOpen,
    involvementOpen, setInvolvementOpen, ungroupedDrawerId, setUngroupedDrawerId, compact,
    flashingIds, pulsedRoles, roles, jiraBaseUrl, period, breakdown, setBreakdown,
    scenario, opoOff, allocations, allocLoading, continuation,
    appearanceValue, liftIncluded, updateAppearance, approve, revert,
    includedIds, personSort, setPersonSort, handleDragEnd, quarterInt,
    resourceBase, resourceSummary, teamAssigneeOptions, isDraft, isApproved, deficit,
    rowStateClass, toggleAllocation, registerRowRef, handlePriorityChange, handleAssigneeChange,
    handleDeveloperChange, hasSubgroups, ungrouped, subgroupOptions,
    neighborsTakenIds, onlyNeighborsTaken, setOnlyNeighborsFor, shownSections, collapsedSections,
    toggleSection, handleSubgroupChange, handleOpenBreakdown, handleApprove, handleRevert,
    handleDelete, handleTeamChange, handleRename, scenarioOptions,
  } = pl;
  const ready = !!scenarioId && !!scenario && !!scenario.team;
  const grid = hasSubgroups ? GRID_Z_SUB : GRID_Z;
  const roleLabels = opoOff ? ['АН', 'ПР', 'ТС'] : ['АН', 'ПР', 'ТС', 'ОПЭ'];

  return (
    <div className="zn-fit plz">
      <ZonesBand title="Сценарии" subtitle={SUBTITLE}>
        <div className="zn-band-row">
          <BandField label="Сценарий">
            <Select
              data-tour="planning-scenario-select"
              variant="borderless"
              style={{ minWidth: 260, maxWidth: 380 }}
              popupMatchSelectWidth={false}
              placeholder="Выберите сценарий"
              value={scenarioId ?? undefined}
              onChange={(v) => setScenarioId(v)}
              options={scenarioOptions}
              allowClear
              onClear={() => setScenarioId(null)}
            />
          </BandField>
          <Tooltip title="Сравнить два сценария">
            <Button icon={<ArrowLeftRight size={15} strokeWidth={1.6} />} onClick={() => setCompareOpen(true)}>
              Сравнить
            </Button>
          </Tooltip>
          <Tooltip title="Вовлечённость и нормированные работы">
            <Button
              icon={<Users size={15} strokeWidth={1.6} />}
              onClick={() => setInvolvementOpen(true)}
              data-tour="planning-involvement"
            >
              Вовлечённость
            </Button>
          </Tooltip>
          <span style={{ flex: 1 }} />
          <Button
            className="zn-btn-dark"
            icon={<Plus size={15} strokeWidth={1.8} />}
            onClick={() => setCreateOpen(true)}
            data-tour="planning-new-scenario"
          >
            Новый сценарий
          </Button>
        </div>
        {ready && (
          <BandTabs
            activeKey={activeTab}
            onChange={(k) => setActiveTab(k as 'distribution' | 'rules')}
            items={[
              { key: 'distribution', label: 'Распределение', tour: 'planning-tab-distribution' },
              { key: 'rules', label: 'Правила', tour: 'planning-tab-rules' },
            ]}
          />
        )}
      </ZonesBand>

      <ScenarioCreateModal
        open={createOpen}
        onClose={(createdId) => {
          setCreateOpen(false);
          if (createdId) setScenarioId(createdId);
        }}
      />

      {!scenarioId && (
        <section className="zn-card plz-empty">
          Сценарии отсутствуют или не выбраны. Нажмите «Новый сценарий», чтобы начать планирование квартала.
        </section>
      )}

      {scenarioId && scenario && !scenario.team && (
        <section className="zn-card plz-team">
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
          <section className="zn-card plz-scenario" aria-label="Сценарий">
            <div className="plz-scenario-row">
              <span data-tour="planning-scenario-name" className="plz-name">
                <Typography.Text editable={{ onChange: handleRename, tooltip: 'Переименовать', maxLength: 200 }}>
                  {scenario.name}
                </Typography.Text>
              </span>
              <span className="plz-period">{scenario.quarter} {scenario.year}</span>
              <span className={`plz-status${isApproved ? ' is-approved' : ''}`}>{isApproved ? 'Утверждён' : 'Черновик'}</span>
              <ScenarioDeficitBadge deficit={deficit} />
              {allocations && (
                <span className="plz-count">включено {includedIds.length} из {allocations.length}</span>
              )}
              <span style={{ flex: 1 }} />
              {isDraft ? (
                ungrouped.length > 0 ? (
                  <Tooltip title={`Сначала проставьте группы: ${ungrouped.map((u) => u.display_name).join(', ')}`}>
                    <span style={{ display: 'inline-block', cursor: 'not-allowed' }}>
                      <Button type="primary" icon={<CheckCircle2 size={14} />} disabled data-tour="planning-approve">
                        Утвердить
                      </Button>
                    </span>
                  </Tooltip>
                ) : (
                  <Button type="primary" onClick={handleApprove} loading={approve.isPending} data-tour="planning-approve">
                    Утвердить
                  </Button>
                )
              ) : (
                <Button icon={<Undo2 size={14} strokeWidth={1.6} />} onClick={handleRevert} loading={revert.isPending} data-tour="planning-revert">
                  В черновик
                </Button>
              )}
              {isApproved && (
                <Button
                  icon={<BarChart3 size={14} strokeWidth={1.6} />}
                  onClick={() => navigate(`/resource-planning?scenario_id=${scenario.id}&quarter=${scenario.quarter}&year=${scenario.year}`)}
                  data-tour="planning-diagram"
                >
                  Диаграмма
                </Button>
              )}
              {isDraft && (
                <Tooltip title="Сравнить с последним утверждённым">
                  <Button icon={<GitCompare size={14} strokeWidth={1.6} />} onClick={() => setDiffOpen(true)}>Diff</Button>
                </Tooltip>
              )}
              <Tooltip title="История ревизий и сравнение снапшотов">
                <Button icon={<History size={14} strokeWidth={1.6} />} onClick={() => setHistoryOpen(true)}>История</Button>
              </Tooltip>
              <Tooltip title="При включении задача поднимается в начало списка">
                <label className="plz-switch" data-tour="planning-lift-toggle">
                  <Switch
                    size="small"
                    checked={liftIncluded}
                    onChange={(value) =>
                      updateAppearance.mutate({ ...appearanceValue, scenario_lift_included: value })}
                  />
                  поднимать наверх
                </label>
              </Tooltip>
              <Button
                icon={<Download size={14} strokeWidth={1.6} />}
                onClick={() => {
                  downloadScenarioXlsx(scenarioId);
                  trackAction('scenario_xlsx_exported', scenarioId);
                }}
              >
                Экспорт
              </Button>
              <Popconfirm title="Удалить сценарий?" description="Вместе с раскладками. Отменить нельзя." onConfirm={handleDelete}>
                <Button danger aria-label="Удалить сценарий" icon={<Trash2 size={15} strokeWidth={1.6} />} />
              </Popconfirm>
            </div>
            {isApproved && <CapacityDriftIndicator scenarioId={scenarioId} />}
          </section>

          <div className="plz-summary">
            <ScenarioResourceSummary
              defaultCollapsed
              scenarioId={scenarioId}
              enabled={!!scenario.team}
              allocations={allocations ?? []}
              employees={resourceBase?.employees}
              pulsedRoles={pulsedRoles}
            />
          </div>

          {activeTab === 'distribution' && neighborsTakenIds.size > 0 && (
            <div className="plz-neighbors">
              <NeighborsTakenBanner
                count={neighborsTakenIds.size}
                onlyThem={onlyNeighborsTaken}
                onOnlyThemChange={(on) => setOnlyNeighborsFor(on ? scenarioId : null)}
              />
            </div>
          )}

          {isDraft && ungrouped.length > 0 && (
            <Alert
              type="error"
              showIcon
              title={`Без группы: ${ungrouped.length} чел. — сценарий нельзя утвердить`}
              description={(
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
              )}
            />
          )}

          <div className="plz-main">
            {activeTab === 'distribution' ? (
              <section className="zn-card plz-table" aria-label="Элементы бэклога">
                <div className="zn-card-head plz-table-head">
                  <h2>Элементы бэклога</h2>
                  <span className="plz-hint">
                    {isApproved ? 'сценарий утверждён — отметки заблокированы' : 'клик по строке переключает включение'}
                  </span>
                  <span style={{ flex: 1 }} />
                  {allocations && (
                    <span className="plz-totals">
                      <b>{allocations.length} идей</b> · включено {includedIds.length}
                    </span>
                  )}
                </div>
                {allocLoading ? (
                  <Spin style={{ display: 'block', margin: '40px auto' }} />
                ) : (
                  <div className="plz-table-scroll">
                    <div style={{ minWidth: gridMinWidth(grid) }}>
                      <div
                        className="plz-grid-head"
                        style={{ gridTemplateColumns: grid, columnGap: GRID_GAP }}
                      >
                        <span aria-hidden />
                        <span title="Включено в сценарий" style={{ textAlign: 'center' }}>Вкл</span>
                        <span title="Приоритет" style={{ textAlign: 'center' }}>Приоритет</span>
                        <span>Идея</span>
                        <SortableHeader sortKey="analyst" sort={personSort} onSort={(k) => setPersonSort((s) => nextPersonSort(s, k))}>
                          Аналитик
                        </SortableHeader>
                        <SortableHeader sortKey="developer" sort={personSort} onSort={(k) => setPersonSort((s) => nextPersonSort(s, k))}>
                          Разработчик
                        </SortableHeader>
                        {hasSubgroups && <span>Группа</span>}
                        <span>Заказчик</span>
                        <div style={{ display: 'flex', gap: 4 }}>
                          {roleLabels.map((l) => (
                            <span key={l} style={{ flex: 1, minWidth: 42, textAlign: 'center' }}>{l}</span>
                          ))}
                        </div>
                        <span style={{ textAlign: 'right' }}>Всего часов</span>
                      </div>
                      <DndContext collisionDetection={closestCenter} modifiers={[restrictToVerticalAxis]} onDragEnd={handleDragEnd}>
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
                                  <SortableContext items={section.items.map((a) => a.id)} strategy={verticalListSortingStrategy}>
                                    <div>
                                      {section.items.map((a) => (
                                        <BacklogAllocRow
                                          key={a.id}
                                          alloc={a}
                                          scenarioId={scenarioId}
                                          scenarioStatus={(scenario.status ?? 'draft') as 'draft' | 'approved'}
                                          isDraft={isDraft}
                                          dragLocked={personSort !== null}
                                          compact={compact}
                                          flashing={flashingIds.has(a.id)}
                                          rowStateClass={rowStateClass(a)}
                                          gridTemplate={grid}
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
                          {(allocations ?? []).length === 0 && (
                            <div className="plz-no-rows">
                              В сценарии нет элементов. Добавьте задачи в бэклог — они появятся автоматически.
                            </div>
                          )}
                        </div>
                      </DndContext>
                    </div>
                  </div>
                )}
                <div className="plz-legend">
                  <span><i className="is-included" />включено</span>
                  <span><i className="is-deficit" />включено при дефиците</span>
                  <span><i className="is-in-work" />квартальная задача уже в работе</span>
                  <span><i className="is-no-est" />нет оценок</span>
                </div>
              </section>
            ) : (
              <section className="zn-card plz-rules" data-tour="planning-rules-card" aria-label="Правила обязательных работ">
                <div className="zn-card-head plz-table-head"><h2>Правила обязательных работ</h2></div>
                <div className="plz-rules-body">
                  <ScenarioRulesEditor scenarioId={scenarioId} />
                </div>
              </section>
            )}

            <aside className="plz-right" aria-label="Ресурс команды">
              <PlanningCapacityPanel
                resourceBase={resourceBase}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
                scenarioId={scenarioId}
                summary={resourceSummary}
              />
              <section className="zn-card plz-qa">
                <ExternalQaInput scenarioId={scenarioId} value={scenario.external_qa_hours} disabled={!isDraft} />
              </section>
            </aside>
          </div>
        </>
      )}

      {scenario && allocations && isDraft && (
        <ScenarioDiffPanel
          open={diffOpen}
          onClose={() => setDiffOpen(false)}
          draftScenario={scenario}
          draftAllocations={allocations}
        />
      )}
      <ScenarioCompareDrawer open={compareOpen} onClose={() => setCompareOpen(false)} initialScenarioId={scenarioId ?? undefined} />
      <ScenarioRevisionHistoryDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} scenarioId={scenarioId} />
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
