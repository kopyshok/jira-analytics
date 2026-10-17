import { Button, Empty, Popover, Segmented, Spin } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import '../warm-layout.css';
import './TeamDeskLayout.css';
import type { DeskLayout, TeamDeskPageState } from '../../../hooks/useTeamDeskPage';
import { DeskFilters } from '../../../components/teamdesk/DeskFilters';
import { ThresholdsPanel } from '../../../components/teamdesk/ThresholdsPanel';
import { DeveloperTable } from '../../../components/teamdesk/DeveloperTable';
import { GroupedIssues } from '../../../components/teamdesk/GroupedIssues';
import { FlagFilterBar } from '../../../components/teamdesk/FlagFilterBar';
import { StatusFilterBar } from '../../../components/teamdesk/StatusFilterBar';
import { WorkloadBars } from '../../../components/teamdesk/WorkloadBars';
import { AbsenceStrip } from '../../../components/teamdesk/AbsenceStrip';
import { ActiveFilters } from '../../../components/teamdesk/ActiveFilters';
import { RubberTasks } from '../../../components/teamdesk/RubberTasks';
import DeskDeveloperCards from '../components/DeskDeveloperCards';

/**
 * «Рабочий стол тимлида» в скине «Тёплая» (макет C-desk): заголовок и
 * раскладки справа, две строки фильтров, плитки разработчиков в ряд (или
 * ведомость), под ними — отборы и таблица задач с закреплённой шапкой, справа —
 * резиновые задачи, задачи в работе и отсутствия. Страница помещается в экран,
 * длинные части прокручиваются внутри своих блоков. Данные и обработчики —
 * общие с раскладкой Aurora (useTeamDeskPage).
 */
export default function WarmTeamDeskLayout({ state }: { state: TeamDeskPageState }) {
  const {
    layout, setLayout, showThresholds, setShowThresholds,
    selectedDev, flagFilter, setFlagFilter, statusFilter, queueScope, selectedName,
    prefs, teams, developers, periodStart, periodEnd, change,
    filterPrefs, settings, overview, data, jiraBaseUrl,
    overrunPct, wipLimit, rubberDays, setDailyRate,
    statusGroups, statusOptions, shownStatuses, totalStatusCounts,
    sprintOptions, releaseOptions, listProps,
    pickStatus, pickStatusForAll, pickQueue, pickFlag, pickDeveloper, resetFilters,
  } = state;
  const loading = overview.isLoading || filterPrefs.isLoading;

  // Пороги и счётчики настраиваются разово — панель живёт за шестерёнкой,
  // всплывает под ней и не сдвигает страницу.
  const settingsButton = (
    <Popover
      trigger="click"
      placement="bottomRight"
      open={showThresholds}
      onOpenChange={setShowThresholds}
      rootClassName="tdc-thresholds-pop"
      content={settings.data ? (
        <ThresholdsPanel
          compact
          key={JSON.stringify([settings.data.thresholds, settings.data.disabled_flags])}
          settings={settings.data}
          statusOptions={statusOptions}
          statusCounters={prefs.status_counters}
          onStatusCountersChange={(value) => change({ status_counters: value })}
        />
      ) : <Spin />}
    >
      <Button icon={<SettingOutlined />} aria-label="Настройки вида" title="Настройки вида" />
    </Popover>
  );

  // Отборы стоят вплотную к таблице задач: влияют они только на неё.
  const filterBars = data && (
    <section className="wr-card tdc-bars" data-tour="desk-flags" aria-label="Отборы">
      <FlagFilterBar
        compact
        flagCounts={data.flag_counts}
        value={flagFilter}
        onChange={setFlagFilter}
      />
      <StatusFilterBar
        compact
        counts={totalStatusCounts}
        // Полоса — фильтр на весь срез: все статусы среза, выбор человека снимается.
        statuses={statusOptions}
        statusGroups={statusGroups}
        value={statusFilter}
        onChange={pickStatusForAll}
      />
      <ActiveFilters
        compact
        developerName={selectedName}
        flag={flagFilter}
        status={statusFilter}
        queueScope={queueScope}
        onReset={resetFilters}
      />
    </section>
  );

  const grouped = layout === 'grouped';
  const issues = data && (
    <div className="tdc-issues-wrap" data-tour="desk-issues">
      {grouped ? (
        <GroupedIssues
          compact
          title="Задачи по разработчикам"
          developers={data.developers}
          issues={data.issues}
          overrunPct={overrunPct}
          jiraBaseUrl={jiraBaseUrl}
          scale="centered"
          flagFilter={flagFilter}
          statusFilter={statusFilter}
          // Разработчик здесь выбирается только кликом по счётчику статуса.
          onlyDeveloper={selectedDev}
          queueScope={queueScope}
          onDailyRate={setDailyRate}
          statuses={shownStatuses}
          statusGroups={statusGroups}
          onStatusFilter={pickStatus}
          {...listProps}
        />
      ) : (
        <GroupedIssues
          compact
          title="Задачи"
          developers={data.developers}
          issues={data.issues}
          overrunPct={overrunPct}
          jiraBaseUrl={jiraBaseUrl}
          onlyDeveloper={selectedDev}
          flagFilter={flagFilter}
          statusFilter={statusFilter}
          queueScope={queueScope}
          onDailyRate={setDailyRate}
          {...listProps}
        />
      )}
    </div>
  );

  return (
    <div className="wr-fit tdc-desk">
      <div className="wr-page-head tdc-head">
        <div>
          <h1 className="wr-h1">Рабочий стол тимлида</h1>
          <p className="wr-subtitle tdc-subtitle">
            Контроль задач в разрезе разработчиков: где стоит, кто не укладывается в оценку,
            что не разбито на подзадачи.
          </p>
        </div>
        <Segmented
          data-tour="desk-tabs"
          className="tdc-tabs"
          aria-label="Раскладка"
          value={layout}
          onChange={(key) => setLayout(key as DeskLayout)}
          options={[
            { value: 'cards', label: 'Светофор' },
            { value: 'table', label: 'Ведомость' },
            { value: 'grouped', label: 'Проблемы вперёд' },
          ]}
        />
      </div>

      <div data-tour="desk-filters" className="tdc-filters-wrap">
        <DeskFilters
          compact
          trailing={settingsButton}
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

      {(loading || !data) && (
        <section className="wr-card tdc-empty-card">
          {loading
            ? <Spin />
            : <Empty description="Выберите команды или добавьте разработчиков" />}
        </section>
      )}

      {data && layout === 'cards' && (
        <DeskDeveloperCards
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
        <section className="wr-card tdc-summary" aria-label="Сводка по разработчикам">
          <h2 className="rpc-card-title">Сводка по разработчикам</h2>
          <div className="tdc-summary-scroll">
            <DeveloperTable
              compact
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
          </div>
        </section>
      )}

      {data && (
        <div className="tdc-body">
          <div className="tdc-main">
            {filterBars}
            {issues}
          </div>
          <aside className="tdc-side" aria-label="Дополнительно">
            <section className="wr-card tdc-side-card" aria-label="Резиновые задачи">
              <RubberTasks
                compact
                issues={data.issues}
                rubberDays={rubberDays}
                jiraBaseUrl={jiraBaseUrl}
                onDailyRate={setDailyRate}
              />
            </section>
            {/* Как у Aurora: в «Проблемах вперёд» полос загрузки нет. */}
            {!grouped && (
              <section className="wr-card tdc-side-card" aria-label="Задач в работе одновременно">
                <h2 className="rpc-card-title">Задач в работе одновременно</h2>
                <WorkloadBars
                  compact
                  developers={data.developers}
                  workload={data.workload}
                  limit={wipLimit}
                />
              </section>
            )}
            <section className="wr-card tdc-side-card" aria-label="Отсутствия">
              <AbsenceStrip compact employeeIds={data.employee_ids ?? {}} />
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
