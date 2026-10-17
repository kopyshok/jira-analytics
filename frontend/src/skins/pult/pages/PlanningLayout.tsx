import { Alert, Button, Empty, Popconfirm, Select, Spin, Switch, Tooltip, Typography } from 'antd';
import { CaretDownOutlined, CaretUpOutlined, DeleteOutlined } from '@ant-design/icons';
import BacklogSections from '../../../components/planning/BacklogSections';
import CapacityDriftIndicator from '../../../components/planning/CapacityDriftIndicator';
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
import NeighborsTakenBanner from '../../../components/planning/NeighborsTakenBanner';
import { TeamSelector } from '../../../components/planning/TeamSelector';
import HoursBreakdownDrawer from '../../../components/hours/HoursBreakdownDrawer';
import EmployeeDrawer from '../../../components/capacity/EmployeeDrawer';
import { downloadScenarioXlsx } from '../../../api/exports';
import { trackAction } from '../../../lib/usage/track';
import { effectiveEstimate } from '../../../utils/allocationEstimates';
import { nextPersonSort, type PersonSortKey } from '../../../utils/allocationSort';
import type { PlanningPageState } from '../../../pages/PlanningPage';
import { PULT_SIGNAL } from '../palette';
import { PcField, PcRow, PcTitle, PModule, PultScreen } from '../ui';

const nf = (v: number) => Math.round(v).toLocaleString('ru-RU');

/**
 * «Сценарии» в обложке «Пульт» (D-scenarios): панель управления, сценарий,
 * сводка ресурса, элементы бэклога, справа ресурс команды / по ролям /
 * по сотрудникам / внешний QA. Данные и обработчики — общий хук страницы.
 */
export default function PultPlanningLayout({ p }: { p: PlanningPageState }) {
  const {
    navigate, scenarioId, setScenarioId, createOpen, setCreateOpen, activeTab, setActiveTab,
    celebrate, diffOpen, setDiffOpen, compareOpen, setCompareOpen, historyOpen, setHistoryOpen,
    involvementOpen, setInvolvementOpen, ungroupedDrawerId, setUngroupedDrawerId,
    pulsedRoles, period, breakdown, setBreakdown, scenario, opoOff, allocations, allocLoading,
    updateAppearance, appearanceValue, liftIncluded, approve, revert, includedIds,
    personSort, setPersonSort, quarterInt, resourceBase, resourceSummary, isDraft, isApproved, deficit,
    hasSubgroups, ungrouped, neighborsTakenIds, onlyNeighborsTaken, setOnlyNeighborsFor,
    handleApprove, handleRevert, handleDelete, handleTeamChange, handleRename, scenarioOptions, gridTemplate, gridGap,
  } = p;

  const sortHead = (key: PersonSortKey, label: string) => {
    const dir = personSort?.key === key ? personSort.dir : null;
    return (
      <span
        role="button"
        tabIndex={0}
        className="sc-sort"
        title="Сортировать: А→Я, Я→А, сброс"
        onClick={() => setPersonSort((s) => nextPersonSort(s, key))}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setPersonSort((s) => nextPersonSort(s, key));
          }
        }}
      >
        {label}
        {dir === 'asc' && <CaretUpOutlined />}
        {dir === 'desc' && <CaretDownOutlined />}
      </span>
    );
  };

  // Итоги включённых — по ролям, как в подписи модуля на макете.
  const totals = (allocations ?? []).filter((a) => a.included).reduce(
    (acc, a) => {
      const e = effectiveEstimate(a);
      acc.an += e.analyst; acc.dev += e.dev; acc.qa += e.qa; acc.opo += e.opo;
      return acc;
    },
    { an: 0, dev: 0, qa: 0, opo: 0 },
  );
  const totalAll = totals.an + totals.dev + totals.qa + (opoOff ? 0 : totals.opo);

  const panel = (
    <PcRow>
      <PcTitle
        eyebrow="Планирование"
        title="Сценарии"
        sub="Отметьте галочками задачи из бэклога — сформируется план квартала"
      />
      <div className="pc-push pc-group sc-panel-tools">
        <PcField label="Сценарий">
          <Select
            data-tour="planning-scenario-select"
            style={{ width: 330 }}
            placeholder="Выберите сценарий"
            value={scenarioId ?? undefined}
            onChange={(v) => setScenarioId(v)}
            options={scenarioOptions}
            allowClear
            onClear={() => setScenarioId(null)}
          />
        </PcField>
        <Tooltip title="Сравнить два сценария">
          <Button onClick={() => setCompareOpen(true)}>Сравнить</Button>
        </Tooltip>
        <Tooltip title="Вовлечённость и нормированные работы">
          <Button onClick={() => setInvolvementOpen(true)} data-tour="planning-involvement">Вовлечённость</Button>
        </Tooltip>
        <Button type="primary" onClick={() => setCreateOpen(true)} data-tour="planning-new-scenario">
          Новый сценарий
        </Button>
      </div>
    </PcRow>
  );

  const dialogs = (
    <>
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
    </>
  );

  if (!scenarioId || !scenario || !scenario.team) {
    return (
      <PultScreen panel={panel} bodyClassName="sc-pult">
        <section className="pm sc-empty">
          {!scenarioId && (
            <Empty description="Сценарии отсутствуют или не выбраны. Нажмите «Новый сценарий», чтобы начать планирование квартала." />
          )}
          {scenarioId && !scenario && <Spin />}
          {scenarioId && scenario && !scenario.team && (
            <div className="sc-team-pick">
              <Alert
                type="info"
                title="Для работы со сценарием выберите команду"
                description="Сценарий привязан к конкретной команде — именно по ней считается ресурс и загрузка."
                showIcon
              />
              <TeamSelector value={scenario.team || null} onChange={handleTeamChange} />
            </div>
          )}
        </section>
        {dialogs}
      </PultScreen>
    );
  }

  return (
    <PultScreen panel={panel} bodyClassName="sc-pult">
      {/* Сценарий: имя, статус, действия */}
      <PModule
        title="Сценарий"
        className="sc-head"
        extra={
          <>
            <span data-tour="planning-scenario-name" className="sc-name">
              <Typography.Text editable={{ onChange: handleRename, tooltip: 'Переименовать', maxLength: 200 }}>
                {scenario.name}
              </Typography.Text>
            </span>
            <span className="num sc-q">{scenario.quarter} {scenario.year}</span>
            <span className={`sc-status${isApproved ? ' is-ok' : ''}`}>{isApproved ? 'УТВЕРЖДЁН' : 'ЧЕРНОВИК'}</span>
            <ScenarioDeficitBadge deficit={deficit} />
            {allocations && (
              <span className="num sc-incl">включено <b>{includedIds.length}</b> из <b>{allocations.length}</b></span>
            )}
            <span className="pm-push sc-actions">
              {isDraft ? (
                ungrouped.length > 0 ? (
                  <Tooltip title={`Сначала проставьте группы: ${ungrouped.map((u) => u.display_name).join(', ')}`}>
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
                <Button onClick={handleRevert} loading={revert.isPending} data-tour="planning-revert">В черновик</Button>
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
                <label className="sc-lift" data-tour="planning-lift-toggle">
                  <Switch
                    checked={liftIncluded}
                    onChange={(value) => updateAppearance.mutate({ ...appearanceValue, scenario_lift_included: value })}
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
              <Popconfirm title="Удалить сценарий?" description="Вместе с раскладками. Отменить нельзя." onConfirm={handleDelete}>
                <Button className="is-key" icon={<DeleteOutlined />} aria-label="Удалить сценарий" />
              </Popconfirm>
            </span>
          </>
        }
      >
        {isApproved && <CapacityDriftIndicator scenarioId={scenarioId} />}
      </PModule>

      {/* Сводка ресурса — та же таблица, что в Aurora (сворачивается) */}
      <section className="pm sc-resource" aria-label="Сводка ресурса">
        <span className="pm-cap sc-resource-cap">Сводка ресурса</span>
        <ScenarioResourceSummary
          scenarioId={scenarioId}
          enabled={!!scenario.team}
          allocations={allocations ?? []}
          employees={resourceBase?.employees}
          pulsedRoles={pulsedRoles}
        />
      </section>

      <div className="sc-tabs-line">
        <div className="sc-tabs" role="tablist" aria-label="Вкладки сценария">
          {(['distribution', 'rules'] as const).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={activeTab === key}
              data-tour={`planning-tab-${key}`}
              className={`p-key${activeTab === key ? ' is-on' : ''}`}
              onClick={() => setActiveTab(key)}
            >
              {key === 'distribution' ? 'Распределение' : 'Правила'}
            </button>
          ))}
        </div>
        {activeTab === 'distribution' && neighborsTakenIds.size > 0 && (
          <div className="sc-neighbors">
            <NeighborsTakenBanner
              count={neighborsTakenIds.size}
              onlyThem={onlyNeighborsTaken}
              onOnlyThemChange={(on) => setOnlyNeighborsFor(on ? scenarioId : null)}
            />
          </div>
        )}
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

      <div className="sc-main">
        {activeTab === 'distribution' ? (
          <PModule
            title="Элементы бэклога"
            className="sc-backlog"
            extra={
              <>
                {allocations && (
                  <span className="pc-count sc-ideas">{allocations.length} идей · включено {includedIds.length}</span>
                )}
                <span className="num sc-roles-sum">
                  АН <b>{nf(totals.an)}</b> · ПР <b>{nf(totals.dev)}</b> · ТС <b>{nf(totals.qa)}</b>
                  {!opoOff && <> · ОПЭ <b>{nf(totals.opo)}</b></>} · <b>{nf(totalAll)} ч</b>
                </span>
                <span className="pm-push sc-hint">
                  {isApproved ? 'сценарий утверждён — отметки заблокированы' : 'клик по строке переключает включение'}
                </span>
              </>
            }
          >
            <div className="pm-screen sc-backlog-screen">
              {allocLoading ? (
                <div className="pm-empty"><Spin /></div>
              ) : (
                <div className="sc-grid" style={{ minWidth: 1180 }}>
                  <div className="sc-grid-head" style={{ display: 'grid', gridTemplateColumns: gridTemplate, columnGap: gridGap }}>
                    <span aria-hidden />
                    <span className="sc-c">Вкл</span>
                    <span className="sc-c">Приор.</span>
                    <span>Идея</span>
                    {sortHead('analyst', 'Аналитик')}
                    {sortHead('developer', 'Разработчик')}
                    {hasSubgroups && <span>Группа</span>}
                    <span>Заказчик</span>
                    <div className="sc-roles-head">
                      {(opoOff ? ['АН', 'ПР', 'ТС'] : ['АН', 'ПР', 'ТС', 'ОПЭ']).map((l) => <span key={l}>{l}</span>)}
                    </div>
                    <span className="sc-r">Всего часов</span>
                  </div>
                  <BacklogSections p={p} />
                </div>
              )}
            </div>
            <div className="pm-legend sc-legend">
              <span className="pc-cap">Маркер</span>
              <span><i style={{ background: PULT_SIGNAL.blue }} />уже в работе</span>
              <span><i className="is-round" style={{ background: PULT_SIGNAL.green }} />включено</span>
              <span><i className="is-ring" />включено при дефиците</span>
              <span><i className="is-empty" />нет оценок</span>
              <span className="pm-push">подложка строки — включено</span>
            </div>
          </PModule>
        ) : (
          <PModule title="Правила обязательных работ" className="sc-rules">
            <div className="pm-screen sc-rules-screen" data-tour="planning-rules-card">
              <ScenarioRulesEditor scenarioId={scenarioId} />
            </div>
          </PModule>
        )}

        <div className="sc-side">
          <PlanningCapacityPanel
            resourceBase={resourceBase}
            allocations={allocations ?? []}
            quarter={String(quarterInt)}
            scenarioId={scenarioId}
            summary={resourceSummary}
          />
          <PModule title="Внешний QA" className="sc-qa">
            <ExternalQaInput scenarioId={scenarioId} value={scenario.external_qa_hours} disabled={!isDraft} />
          </PModule>
        </div>
      </div>
      {dialogs}
    </PultScreen>
  );
}
