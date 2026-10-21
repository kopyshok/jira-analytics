import { Alert, Button, Checkbox, Popconfirm, Select, Spin, Tooltip, Typography } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { PlanningPageModel } from '../../../hooks/usePlanningPage';
import PlanningCapacityPanel from '../../../components/planning/PlanningCapacityPanel';
import ScenarioRulesEditor from '../../../components/planning/ScenarioRulesEditor';
import ExternalQaInput from '../../../components/planning/ExternalQaInput';
import ScenarioResourceSummary from '../../../components/planning/ScenarioResourceSummary';
import ScenarioDeficitBadge from '../../../components/planning/ScenarioDeficitBadge';
import CapacityDriftIndicator from '../../../components/planning/CapacityDriftIndicator';
import ScenarioBacklogTable from '../../../components/planning/ScenarioBacklogTable';
import NeighborsTakenBanner from '../../../components/planning/NeighborsTakenBanner';
import { TeamSelector } from '../../../components/planning/TeamSelector';
import { planningOverlays } from '../../../components/planning/planningOverlays';
import { includedHours } from '../../../utils/planning';
import { getRoleLabel } from '../../../utils/roles';
import { BlockHead, Figure, Figures, PassportStrip, StripCell, SwissData, SwissPage } from '../components/Passport';
import './planning.css';

const num = (v: number) => Math.round(v).toLocaleString('ru-RU');

/** Счёт идей: «1 идея», «3 идеи», «31 идея», «12 идей». */
function ideasWord(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'идея';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'идеи';
  return 'идей';
}

/** После «из N»: «из 31 идеи», «из 5 идей». */
const ideasOf = (n: number) => (n % 10 === 1 && n % 100 !== 11 ? 'идеи' : 'идей');

const ROLE_SHORT: Record<string, string> = {
  analyst: 'АН', dev: 'ПР', qa: 'ТС', RP: 'РП', project_manager: 'РП', consultant: 'КС',
};

/**
 * «Сценарии» в обложке «Швейцарская» (макет G-scenarios): паспорт полосой под
 * меню — ресурс на бэклог, включено идей, самый большой дефицит, выбор сценария;
 * ниже во всю ширину — шапка сценария 2.2, строка сводки ресурса, вкладки 2.3/2.4,
 * таблица бэклога 2.5 и колонка ресурса команды 2.6–2.9.
 */
export default function SwissPlanningLayout({ vm }: { vm: PlanningPageModel }) {
  const {
    navigate, scenarioId, setScenarioId, scenario, scenarioOptions, setCompareOpen, setInvolvementOpen,
    setCreateOpen, handleTeamChange, handleRename, isApproved, isDraft, deficit, allocations, includedIds,
    ungrouped, handleApprove, approve, handleRevert, revert, openDiagram, setDiffOpen, setHistoryOpen,
    liftIncluded, setLiftIncluded, handleExport, handleDelete, resourceBase, pulsedRoles, activeTab,
    setActiveTab, setUngroupedDrawerId, allocLoading, quarterInt, resourceSummary, roles, opoOff,
    neighborsTakenIds, onlyNeighborsTaken, setOnlyNeighborsTaken,
  } = vm;
  const overlays = planningOverlays(vm);
  const ready = !!scenarioId && !!scenario && !!scenario.team;

  const backlog = resourceSummary?.available_for_backlog_total;
  const deficits = Object.entries(deficit).filter(([, h]) => h > 0).sort(([, a], [, b]) => b - a);
  const [worstRole, worstHours] = deficits[0] ?? [];
  const short = (role: string) => ROLE_SHORT[role] ?? getRoleLabel(roles, role).slice(0, 2);
  const restDeficits = deficits.slice(1).map(([r, h]) => `${short(r)} −${num(h)} ч`).join(', ');
  const hours = includedHours(allocations ?? [], opoOff);

  return (
    <>
      <SwissPage strip className="sw-pl">
        <PassportStrip
          eyebrow="2.0 Планирование · паспорт экрана"
          title="Сценарии"
          hint="Отметьте галочками задачи из бэклога — сформируется план квартала."
        >
          <StripCell>
            <Figures className="sw-pl-figures">
              <Figure value={backlog == null ? '—' : `${num(backlog)} ч`} caption="на бэклог" />
              <Figure
                value={allocations ? `${includedIds.length} из ${allocations.length}` : '—'}
                caption={`${allocations ? ideasOf(allocations.length) : 'идей'} включено в сценарий`}
              />
              {worstRole ? (
                <Figure
                  tone="accent"
                  strong
                  value={`−${num(worstHours as number)} ч ${short(worstRole)}`}
                  caption={`Дефицит по роли «${getRoleLabel(roles, worstRole)}»${restDeficits ? `; ещё ${restDeficits}` : ''}`}
                />
              ) : ready ? (
                <Figure tone="good" value="0 ч" caption="дефицита нет" />
              ) : (
                // Сценарий не выбран или без команды — дефицит не считается, цифры нет.
                <Figure value="—" caption="дефицит" />
              )}
            </Figures>
          </StripCell>

          <StripCell className="sw-pl-pick" label="Выбор сценария">
            <Select
              data-tour="planning-scenario-select"
              variant="underlined"
              aria-label="Выбор сценария"
              placeholder="Выберите сценарий"
              value={scenarioId ?? undefined}
              onChange={(v) => setScenarioId(v)}
              options={scenarioOptions}
              allowClear
              onClear={() => setScenarioId(null)}
              popupMatchSelectWidth={false}
            />
          </StripCell>

          <StripCell className="sw-strip-cell--btn sw-pl-pass-btns">
            <Tooltip title="Сравнить два сценария">
              <Button onClick={() => setCompareOpen(true)}>Сравнить</Button>
            </Tooltip>
            <Tooltip title="Вовлечённость и нормированные работы">
              <Button onClick={() => setInvolvementOpen(true)} data-tour="planning-involvement">
                Вовлечённость
              </Button>
            </Tooltip>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              className="sw-pl-new"
              onClick={() => setCreateOpen(true)}
              data-tour="planning-new-scenario"
            >
              Новый сценарий
            </Button>
          </StripCell>
        </PassportStrip>

        <SwissData className="sw-pl-data">
          {!scenarioId && (
            <div className="sw-empty">
              Сценарии отсутствуют или не выбраны. Нажмите «Новый сценарий», чтобы начать планирование квартала.
            </div>
          )}

          {scenarioId && scenario && !scenario.team && (
            <section className="sw-block">
              <Alert
                type="info"
                title="Для работы со сценарием выберите команду"
                description="Сценарий привязан к конкретной команде — именно по ней считается ресурс и загрузка."
                showIcon
              />
              <TeamSelector value={scenario.team || null} onChange={handleTeamChange} />
            </section>
          )}

          {ready && scenario && scenarioId && (
            <>
              <header className="sw-pl-head">
                <div className="sw-pl-head-main">
                  <span className="sw-block-num">2.2</span>
                  <span data-tour="planning-scenario-name" className="sw-pl-name">
                    <Typography.Text editable={{ onChange: handleRename, tooltip: 'Переименовать', maxLength: 200 }}>
                      {scenario.name}
                    </Typography.Text>
                  </span>
                  <span className="sw-pl-quarter">{scenario.quarter} {scenario.year}</span>
                  <span className={`sw-chip${isApproved ? ' is-good' : ''}`}>{isApproved ? 'Утверждён' : 'Черновик'}</span>
                  <ScenarioDeficitBadge deficit={deficit} />
                  {allocations && (
                    <span className="sw-pl-count">включено {includedIds.length} из {allocations.length}</span>
                  )}
                </div>
                <div className="sw-pl-actions">
                  {isDraft ? (
                    ungrouped.length > 0 ? (
                      <Tooltip title={`Сначала проставьте группы: ${ungrouped.map((u) => u.display_name).join(', ')}`}>
                        <span style={{ display: 'inline-block', cursor: 'not-allowed' }}>
                          <Button type="primary" size="small" disabled data-tour="planning-approve">Утвердить</Button>
                        </span>
                      </Tooltip>
                    ) : (
                      <Button type="primary" size="small" onClick={handleApprove} loading={approve.isPending} data-tour="planning-approve">
                        Утвердить
                      </Button>
                    )
                  ) : (
                    <Button size="small" onClick={handleRevert} loading={revert.isPending} data-tour="planning-revert">
                      В черновик
                    </Button>
                  )}
                  {isApproved && (
                    <Button size="small" onClick={openDiagram} data-tour="planning-diagram">Диаграмма</Button>
                  )}
                  {isDraft && (
                    <Tooltip title="Сравнить с последним утверждённым">
                      <Button size="small" onClick={() => setDiffOpen(true)}>Diff</Button>
                    </Tooltip>
                  )}
                  <Tooltip title="История ревизий и сравнение снапшотов">
                    <Button size="small" onClick={() => setHistoryOpen(true)}>История</Button>
                  </Tooltip>
                  <Tooltip title="При включении задача поднимается в начало списка">
                    <Checkbox
                      data-tour="planning-lift-toggle"
                      checked={liftIncluded}
                      onChange={(e) => setLiftIncluded(e.target.checked)}
                    >
                      поднимать наверх
                    </Checkbox>
                  </Tooltip>
                  <Button size="small" onClick={handleExport}>Экспорт</Button>
                  <Popconfirm
                    title="Удалить сценарий?"
                    description="Вместе с раскладками. Отменить нельзя."
                    onConfirm={handleDelete}
                  >
                    <Button size="small" className="sw-pl-delete" aria-label="Удалить сценарий" icon={<DeleteOutlined />} />
                  </Popconfirm>
                </div>
              </header>
              {isApproved && <CapacityDriftIndicator scenarioId={scenarioId} />}

              <ScenarioResourceSummary
                variant="line"
                scenarioId={scenarioId}
                enabled
                allocations={allocations ?? []}
                employees={resourceBase?.employees}
                pulsedRoles={pulsedRoles}
              />

              <div role="tablist" aria-label="Раздел сценария" className="sw-tabs">
                {(['distribution', 'rules'] as const).map((key, i) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === key}
                    className={activeTab === key ? 'is-active' : undefined}
                    data-tour={`planning-tab-${key}`}
                    onClick={() => setActiveTab(key)}
                  >
                    <span className="sw-tab-num">2.{3 + i}</span>
                    {key === 'distribution' ? 'Распределение' : 'Правила'}
                  </button>
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
              {activeTab === 'distribution' && neighborsTakenIds.size > 0 && (
                <NeighborsTakenBanner
                  count={neighborsTakenIds.size}
                  onlyThem={onlyNeighborsTaken}
                  onOnlyThemChange={setOnlyNeighborsTaken}
                />
              )}

              <div className="sw-pl-grid">
                {activeTab === 'distribution' ? (
                  <section className="sw-block sw-pl-table">
                    <BlockHead
                      num="2.5"
                      title="Элементы бэклога"
                      size="lg"
                      meta={isApproved ? 'сценарий утверждён — отметки заблокированы' : 'клик по строке переключает включение'}
                    >
                      {allocations && (
                        <span className="sw-pl-totals">
                          {allocations.length} {ideasWord(allocations.length)} · включено {includedIds.length} · АН {num(hours.analyst)} · ПР {num(hours.dev)}
                          {' '}· ТС {num(hours.qa)}{opoOff ? '' : ` · ОПЭ ${num(hours.opo)}`} · <b>{num(hours.total)} ч</b>
                        </span>
                      )}
                    </BlockHead>
                    {allocLoading ? (
                      <div className="sw-empty"><Spin /></div>
                    ) : (
                      <ScenarioBacklogTable vm={vm} variant="table" />
                    )}
                    <div className="sw-legend sw-pl-legend">
                      <span>Состояние:</span>
                      <span><i className="is-in" />включено</span>
                      <span><i className="is-deficit" />включено при дефиците</span>
                      <span><i className="is-work" />квартальная задача уже в работе</span>
                      <span><i className="is-none" />нет оценок</span>
                    </div>
                  </section>
                ) : (
                  <section className="sw-block sw-pl-rules" data-tour="planning-rules-card">
                    <BlockHead num="2.4" title="Правила обязательных работ" size="lg" />
                    <div className="sw-pl-rules-body">
                      <ScenarioRulesEditor scenarioId={scenarioId} />
                    </div>
                  </section>
                )}

                <aside className="sw-pl-side">
                  <PlanningCapacityPanel
                    resourceBase={resourceBase}
                    allocations={allocations ?? []}
                    quarter={String(quarterInt)}
                    scenarioId={scenarioId}
                    summary={resourceSummary}
                  />
                  <section className="sw-block sw-pl-ext">
                    <BlockHead num="2.9" title="Внешний QA" />
                    <ExternalQaInput
                      scenarioId={scenarioId}
                      value={scenario.external_qa_hours}
                      disabled={!isDraft}
                    />
                  </section>
                </aside>
              </div>
            </>
          )}
        </SwissData>
      </SwissPage>
      {overlays.create}
      {overlays.rest}
    </>
  );
}
