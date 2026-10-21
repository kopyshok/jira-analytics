import { Card, Empty, Space, Spin, Tabs, Typography } from 'antd';
import { DeskFilters } from '../components/teamdesk/DeskFilters';
import { ThresholdsPanel } from '../components/teamdesk/ThresholdsPanel';
import { DeveloperCards } from '../components/teamdesk/DeveloperCards';
import { DeveloperTable } from '../components/teamdesk/DeveloperTable';
import { GroupedIssues } from '../components/teamdesk/GroupedIssues';
import { FlagFilterBar } from '../components/teamdesk/FlagFilterBar';
import { StatusFilterBar } from '../components/teamdesk/StatusFilterBar';
import { WorkloadBars } from '../components/teamdesk/WorkloadBars';
import { AbsenceStrip } from '../components/teamdesk/AbsenceStrip';
import { ActiveFilters } from '../components/teamdesk/ActiveFilters';
import { RubberTasks } from '../components/teamdesk/RubberTasks';
import { useSkin } from '../contexts/ThemeContext';
import { useTeamDeskPage, type DeskLayout, type TeamDeskPageState } from '../hooks/useTeamDeskPage';
import PultTeamDeskLayout from '../skins/pult/pages/TeamDeskLayout';

function AuroraTeamDeskLayout({ desk }: { desk: TeamDeskPageState }) {
  const {
    showThresholds, selectedDev, flagFilter, setFlagFilter, statusFilter, queueScope,
    layout, setLayout, filterPrefs, prefs, change, settings, jiraBaseUrl, overview, data,
    overrunPct, wipLimit, rubberDays, setDailyRate,
    statusGroups, statusOptions, shownStatuses, statusBarCounts,
    listProps, pickStatus, pickQueue, pickFlag, resetFilters, pickDeveloper, pickTotalStatus,
    selectedName, filterProps,
  } = desk;

  // Отборы стоят вплотную к таблице задач: влияют они только на неё.
  const filterBars = data && (
    <div data-tour="desk-flags" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <FlagFilterBar
        flagCounts={data.flag_counts}
        value={flagFilter}
        onChange={setFlagFilter}
      />
      <StatusFilterBar
        counts={statusBarCounts}
        // Показываем все статусы среза, иначе выбор счётчиков отнимал бы
        // фильтрацию по остальным статусам.
        statuses={statusOptions}
        statusGroups={statusGroups}
        value={statusFilter}
        // Статус ложится поверх уже выбранных человека и замечания, не сбрасывая их.
        onChange={pickTotalStatus}
      />
      <ActiveFilters
        developerName={selectedName}
        flag={flagFilter}
        status={statusFilter}
        queueScope={queueScope}
        onReset={resetFilters}
      />
    </div>
  );

  // Резиновые задачи стоят сразу за разрезом по людям: тимлид видит, из-за
  // каких задач очередь считается по норме, до того как начнёт фильтровать.
  const rubberCard = data && (
    <RubberTasks
      issues={data.issues}
      rubberDays={rubberDays}
      jiraBaseUrl={jiraBaseUrl}
      onDailyRate={setDailyRate}
    />
  );

  const detailBlocks = (
    <>
      {rubberCard}
      {filterBars}
      <div data-tour="desk-issues">
      <GroupedIssues
        title="Задачи"
        developers={data?.developers ?? []}
        issues={data?.issues ?? []}
        overrunPct={overrunPct}
        jiraBaseUrl={jiraBaseUrl}
        onlyDeveloper={selectedDev}
        flagFilter={flagFilter}
        statusFilter={statusFilter}
        queueScope={queueScope}
        onDailyRate={setDailyRate}
        {...listProps}
      />
      </div>
      <Card size="small" title="Задач в работе одновременно">
        <WorkloadBars
          developers={data?.developers ?? []}
          workload={data?.workload ?? {}}
          limit={wipLimit}
        />
      </Card>
    </>
  );

  return (
    <Space orientation="vertical" size={14} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ margin: 0 }}>Рабочий стол тимлида</Typography.Title>
        <Typography.Text type="secondary">
          Контроль задач в разрезе разработчиков: где стоит, кто не укладывается в оценку,
          что не разбито на подзадачи.
        </Typography.Text>
      </div>

      <div data-tour="desk-filters">
      <DeskFilters {...filterProps} />
      </div>

      {showThresholds && settings.data && (
        <ThresholdsPanel
          key={JSON.stringify([settings.data.thresholds, settings.data.disabled_flags])}
          settings={settings.data}
          statusOptions={statusOptions}
          statusCounters={prefs.status_counters}
          onStatusCountersChange={(value) => change({ status_counters: value })}
        />
      )}

      <Tabs
        data-tour="desk-tabs"
        activeKey={layout}
        onChange={(key) => setLayout(key as DeskLayout)}
        items={[
          { key: 'cards', label: 'Светофор' },
          { key: 'table', label: 'Ведомость' },
          { key: 'grouped', label: 'Проблемы вперёд' },
        ]}
      />

      {(overview.isLoading || filterPrefs.isLoading) && <Spin />}
      {!overview.isLoading && !filterPrefs.isLoading && !data && (
        <Empty description="Выберите команды или добавьте разработчиков" />
      )}

      {data && layout === 'cards' && (
        <>
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
          {detailBlocks}
        </>
      )}

      {data && layout === 'table' && (
        <>
          <Card size="small" title="Сводка по разработчикам">
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
          {detailBlocks}
        </>
      )}

      {data && layout === 'grouped' && rubberCard}
      {data && layout === 'grouped' && filterBars}
      {data && layout === 'grouped' && (
        <div data-tour="desk-issues">
          <GroupedIssues
            title="Задачи по разработчикам"
            developers={data.developers}
            issues={data.issues}
            overrunPct={overrunPct}
            jiraBaseUrl={jiraBaseUrl}
            scale="centered"
            flagFilter={flagFilter}
            statusFilter={statusFilter}
            // Разработчик здесь выбирается только кликом по счётчику статуса —
            // карточек в этой раскладке нет.
            onlyDeveloper={selectedDev}
            queueScope={queueScope}
            onDailyRate={setDailyRate}
            statuses={shownStatuses}
            statusGroups={statusGroups}
            onStatusFilter={pickStatus}
            {...listProps}
          />
        </div>
      )}


      {data && (
        <Card size="small" title="Отсутствия">
          <AbsenceStrip employeeIds={data.employee_ids ?? {}} />
        </Card>
      )}
    </Space>
  );
}

export default function TeamDeskPage() {
  const desk = useTeamDeskPage();
  const skin = useSkin();
  if (skin === 'pult') return <PultTeamDeskLayout desk={desk} />;
  return <AuroraTeamDeskLayout desk={desk} />;
}
