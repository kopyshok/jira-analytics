import { Card, Empty, Spin } from 'antd';
import './team-desk.css';
import { DeskFilters } from '../../../components/teamdesk/DeskFilters';
import { ThresholdsPanel } from '../../../components/teamdesk/ThresholdsPanel';
import { DeveloperTable } from '../../../components/teamdesk/DeveloperTable';
import { GroupedIssues } from '../../../components/teamdesk/GroupedIssues';
import { WorkloadBars } from '../../../components/teamdesk/WorkloadBars';
import { AbsenceStrip } from '../../../components/teamdesk/AbsenceStrip';
import { RubberTasks } from '../../../components/teamdesk/RubberTasks';
import type { DeskLayout, TeamDeskPageState } from '../../../hooks/useTeamDeskPage';
import ZonesBand, { BandTabs } from '../ZonesBand';
import { DeskDevCards } from './desk/DeskDevCards';
import { DeskAttention } from './desk/DeskAttention';

const SUBTITLE = 'Контроль задач в разрезе разработчиков: где стоит, кто не укладывается в оценку, что не разбито на подзадачи.';

/**
 * «Рабочий стол тимлида» в скине «Цветовые зоны»: отборы и раскладки — в
 * полосе зоны; в теле лента плиток, под ней отборы и таблица задач, справа —
 * резиновые задачи, задачи в работе и отсутствия. Экран — в высоту окна.
 */
export default function TeamDeskZonesLayout({ desk }: { desk: TeamDeskPageState }) {
  const {
    showThresholds, setShowThresholds, selectedDev, flagFilter, setFlagFilter, statusFilter,
    queueScope, layout, setLayout, filterPrefs, prefs, teams, developers, periodStart, periodEnd,
    change, settings, jiraBaseUrl, overview, data, overrunPct, wipLimit, rubberDays, setDailyRate,
    statusGroups, statusOptions, shownStatuses, totalStatusCounts, sprintOptions, releaseOptions,
    listProps, pickStatus, pickQueue, pickFlag, resetFilters, pickDeveloper, pickSliceStatus,
    selectedName,
  } = desk;
  const loading = overview.isLoading || filterPrefs.isLoading;

  return (
    <div className="zn-fit dz">
      <ZonesBand title="Рабочий стол тимлида" subtitle={SUBTITLE}>
        <div data-tour="desk-filters">
          <DeskFilters
            variant="band"
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
        <BandTabs
          data-tour="desk-tabs"
          activeKey={layout}
          onChange={(key) => setLayout(key as DeskLayout)}
          items={[
            { key: 'cards', label: 'Светофор' },
            { key: 'table', label: 'Ведомость' },
            { key: 'grouped', label: 'Проблемы вперёд' },
          ]}
        />
      </ZonesBand>

      {showThresholds && settings.data && (
        <div className="dz-thresholds">
          <ThresholdsPanel
            key={JSON.stringify([settings.data.thresholds, settings.data.disabled_flags])}
            settings={settings.data}
            statusOptions={statusOptions}
            statusCounters={prefs.status_counters}
            onStatusCountersChange={(value) => change({ status_counters: value })}
          />
        </div>
      )}

      {loading && <Spin style={{ display: 'block', margin: '60px auto' }} />}
      {!loading && !data && (
        <section className="zn-card dz-empty">
          <Empty description="Выберите команды или добавьте разработчиков" />
        </section>
      )}

      {data && layout === 'cards' && (
        <DeskDevCards
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
      )}
      {data && layout === 'table' && (
        <Card size="small" title="Сводка по разработчикам" className="dz-summary">
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
        </Card>
      )}

      {data && (
        <div className="dz-main">
          <div className="dz-left">
            <DeskAttention
              flagCounts={data.flag_counts}
              flag={flagFilter}
              onFlag={setFlagFilter}
              statusCounts={totalStatusCounts}
              statuses={statusOptions}
              statusGroups={statusGroups}
              status={statusFilter}
              onStatus={pickSliceStatus}
              developerName={selectedName}
              queueScope={queueScope}
              onReset={resetFilters}
            />
            <div data-tour="desk-issues" className="dz-issues">
              <GroupedIssues
                compact
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
                {...(layout === 'grouped'
                  ? { statuses: shownStatuses, statusGroups, onStatusFilter: pickStatus }
                  : {})}
                {...listProps}
              />
            </div>
          </div>
          <aside className="dz-right" aria-label="Дополнительные блоки">
            <RubberTasks
              compact
              issues={data.issues}
              rubberDays={rubberDays}
              jiraBaseUrl={jiraBaseUrl}
              onDailyRate={setDailyRate}
            />
            {layout !== 'grouped' && (
              <Card size="small" title={`Задач в работе одновременно · лимит ${wipLimit}`} className="dz-wip">
                <WorkloadBars
                  developers={data.developers}
                  workload={data.workload ?? {}}
                  limit={wipLimit}
                />
              </Card>
            )}
            <Card size="small" title="Отсутствия" className="dz-absence">
              <AbsenceStrip compact employeeIds={data.employee_ids ?? {}} />
            </Card>
          </aside>
        </div>
      )}
    </div>
  );
}
