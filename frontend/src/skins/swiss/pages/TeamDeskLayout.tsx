import { Empty, Spin } from 'antd';
import type { TeamDeskPageModel, DeskLayout } from '../../../hooks/useTeamDeskPage';
import { DeskFilters } from '../../../components/teamdesk/DeskFilters';
import { ThresholdsPanel } from '../../../components/teamdesk/ThresholdsPanel';
import { DeveloperCards } from '../../../components/teamdesk/DeveloperCards';
import { DeveloperTable } from '../../../components/teamdesk/DeveloperTable';
import { GroupedIssues } from '../../../components/teamdesk/GroupedIssues';
import { FlagFilterBar } from '../../../components/teamdesk/FlagFilterBar';
import { StatusFilterBar } from '../../../components/teamdesk/StatusFilterBar';
import { WorkloadBars } from '../../../components/teamdesk/WorkloadBars';
import { AbsenceStrip } from '../../../components/teamdesk/AbsenceStrip';
import { ActiveFilters } from '../../../components/teamdesk/ActiveFilters';
import { RubberTasks } from '../../../components/teamdesk/RubberTasks';
import { deskTaskCount, developersWord, tasksWord, teamAccuracy } from '../../../utils/deskSummary';
import { BlockHead, Figure, Figures, PassSection, Passport, SwissData, SwissPage } from '../components/Passport';
import './teamDesk.css';

const TABS: { key: DeskLayout; num: string; label: string }[] = [
  { key: 'cards', num: '1.1', label: 'Светофор' },
  { key: 'table', num: '1.2', label: 'Ведомость' },
  { key: 'grouped', num: '1.3', label: 'Проблемы вперёд' },
];

/**
 * «Рабочий стол тимлида» в обложке «Швейцарская»: паспорт (цифры среза и
 * отбор столбиком), справа вкладки-разрезы, плитки людей, список задач и
 * узкая колонка — резиновые задачи, задачи в работе, отсутствия.
 */
export default function SwissTeamDeskLayout({ vm }: { vm: TeamDeskPageModel }) {
  const {
    showThresholds, setShowThresholds,
    selectedDev, flagFilter, setFlagFilter, statusFilter, queueScope,
    layout, setLayout, filterPrefs, prefs, teams, developers, periodStart, periodEnd, change,
    settings, jiraBaseUrl, overview, data, overrunPct, wipLimit, rubberDays, setDailyRate,
    statusGroups, statusOptions, shownStatuses, totalStatusCounts,
    sprintOptions, releaseOptions, listProps,
    pickStatus, pickQueue, pickFlag, resetFilters, pickDeveloper, pickSliceStatus, selectedName,
  } = vm;
  const loading = overview.isLoading || filterPrefs.isLoading;
  const tasks = data ? deskTaskCount(data.developers) : null;
  const people = data?.developers.length ?? null;
  const over = data?.flag_counts.over ?? 0;
  const accuracy = data ? teamAccuracy(data.issues) : null;

  const issuesBlock = data && (
    <div data-tour="desk-issues" className="sw-desk-issues">
      <GroupedIssues
        title={layout === 'grouped' ? 'Задачи по разработчикам' : 'Задачи'}
        developers={data.developers}
        issues={data.issues}
        overrunPct={overrunPct}
        jiraBaseUrl={jiraBaseUrl}
        scale={layout === 'grouped' ? 'centered' : 'bar'}
        onlyDeveloper={selectedDev}
        flagFilter={flagFilter}
        statusFilter={statusFilter}
        queueScope={queueScope}
        onDailyRate={setDailyRate}
        groupToggle="segmented"
        {...(layout === 'grouped'
          ? { statuses: shownStatuses, statusGroups, onStatusFilter: pickStatus }
          : {})}
        {...listProps}
      />
    </div>
  );

  return (
    <SwissPage className="sw-desk">
      <Passport
        eyebrow="1.0 Паспорт экрана"
        title="Рабочий стол тимлида"
        subtitle="Контроль задач в разрезе разработчиков: где стоит, кто не укладывается в оценку, что не разбито на подзадачи."
      >
        <Figures>
          <Figure value={tasks ?? '—'} caption={tasks == null ? 'задач' : tasksWord(tasks)} />
          <Figure value={people ?? '—'} caption={people == null ? 'разработчиков' : developersWord(people)} />
          <Figure
            value={data ? over : '—'}
            caption={`Перерасход · ${over}`}
            tone={over > 0 ? 'accent' : undefined}
            strong
          />
          <Figure
            value={accuracy == null ? '—' : `×${accuracy.toFixed(2)}`}
            caption="Точность, общая"
            title="Медиана «факт / оценка» по задачам среза с оценкой и списаниями"
          />
        </Figures>

        <PassSection eyebrow="1.1 Отбор">
          <div data-tour="desk-filters">
            <DeskFilters
              variant="stack"
              teams={teams}
              onTeamsChange={(value) => change({ teams: value })}
              developers={developers}
              onDevelopersChange={(value) => change({ developers: value })}
              developerRoles={settings.data?.developer_roles ?? ['dev']}
              mode={prefs.mode}
              onModeChange={(value) => change({ mode: value })}
              periodStart={periodStart}
              periodEnd={periodEnd}
              onPeriodChange={(start, end) => change({ period_start: start, period_end: end })}
              showReviewed={prefs.show_reviewed}
              onShowReviewedChange={(value) => change({ show_reviewed: value })}
              showDoneSubtasks={prefs.show_done_subtasks}
              onShowDoneSubtasksChange={(value) => change({ show_done_subtasks: value })}
              onToggleThresholds={() => setShowThresholds((v) => !v)}
              sprintOptions={sprintOptions}
              releaseOptions={releaseOptions}
              sprints={prefs.sprints}
              onSprintsChange={(value) => change({ sprints: value })}
              releases={prefs.releases}
              onReleasesChange={(value) => change({ releases: value })}
            />
          </div>
        </PassSection>
      </Passport>

      <SwissData className="sw-desk-data">
        {showThresholds && settings.data && (
          <div className="sw-desk-thresholds">
            <ThresholdsPanel
              key={JSON.stringify([settings.data.thresholds, settings.data.disabled_flags])}
              settings={settings.data}
              statusOptions={statusOptions}
              statusCounters={prefs.status_counters}
              onStatusCountersChange={(value) => change({ status_counters: value })}
            />
          </div>
        )}

        <div role="tablist" aria-label="Раскладка" className="sw-tabs" data-tour="desk-tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={layout === t.key}
              className={layout === t.key ? 'is-active' : undefined}
              onClick={() => setLayout(t.key)}
            >
              <span className="sw-tab-num">{t.num}</span>{t.label}
            </button>
          ))}
        </div>

        {loading && <Spin />}
        {!loading && !data && <Empty description="Выберите команды или добавьте разработчиков" />}

        {data && layout === 'cards' && (
          <div className="sw-desk-cards">
            <DeveloperCards
              developers={data.developers}
              workload={data.workload}
              overrunPct={overrunPct}
              selected={selectedDev}
              onSelect={pickDeveloper}
              statuses={shownStatuses}
              statusGroups={statusGroups}
              statusFilter={statusFilter}
              onStatusFilter={pickStatus}
              queueScope={queueScope}
              onQueueFilter={pickQueue}
              flagFilter={flagFilter}
              onFlagFilter={pickFlag}
            />
          </div>
        )}
        {data && layout === 'table' && (
          <section className="sw-block sw-desk-summary">
            <BlockHead num="1.2" title="Сводка по разработчикам" />
            <DeveloperTable
              developers={data.developers}
              workload={data.workload}
              overrunPct={overrunPct}
              selected={selectedDev}
              onSelect={pickDeveloper}
              statuses={shownStatuses}
              onStatusFilter={pickStatus}
              queueScope={queueScope}
              onQueueFilter={pickQueue}
              flagFilter={flagFilter}
              onFlagFilter={pickFlag}
            />
          </section>
        )}

        {data && (
          <div className="sw-desk-bottom">
            <div className="sw-desk-main">
              <div data-tour="desk-flags" className="sw-desk-bars">
                <FlagFilterBar flagCounts={data.flag_counts} value={flagFilter} onChange={setFlagFilter} />
                <StatusFilterBar
                  counts={totalStatusCounts}
                  statuses={statusOptions}
                  statusGroups={statusGroups}
                  value={statusFilter}
                  onChange={pickSliceStatus}
                />
                <ActiveFilters
                  developerName={selectedName}
                  flag={flagFilter}
                  status={statusFilter}
                  queueScope={queueScope}
                  onReset={resetFilters}
                />
              </div>
              {issuesBlock}
            </div>
            <aside className="sw-desk-side">
              <RubberTasks
                compact
                issues={data.issues}
                rubberDays={rubberDays}
                jiraBaseUrl={jiraBaseUrl}
                onDailyRate={setDailyRate}
              />
              {layout !== 'grouped' && (
                <section className="desk-wip-block">
                  <div className="sw-block-title"><span className="sw-block-num">1.6</span><b>Задач в работе одновременно</b></div>
                  <WorkloadBars developers={data.developers} workload={data.workload} limit={wipLimit} />
                </section>
              )}
              <AbsenceStrip compact employeeIds={data.employee_ids ?? {}} />
            </aside>
          </div>
        )}
      </SwissData>
    </SwissPage>
  );
}
