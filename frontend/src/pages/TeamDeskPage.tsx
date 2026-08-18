import { useEffect, useState } from 'react';
import { Card, Empty, Space, Spin, Tabs, Typography } from 'antd';
import teamDeskHelp from '../../../docs/help/team-desk.md?raw';
import {
  orderedStatuses, type DeskFilterPrefs, type FlagCode,
} from '../api/teamDesk';
import { useRegisterHelp } from '../contexts/HelpContext';
import {
  useDeskFilter, useDeskOverview, useDeskSettings, useSaveDailyRate, useSaveDeskFilter,
} from '../hooks/useTeamDesk';
import { useJiraBaseUrl } from '../hooks/useSettings';
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
import type { QueueScope } from '../components/teamdesk/queueFilter';

type Layout = 'cards' | 'table' | 'grouped';
const LAYOUT_KEY = 'team-desk-layout';

/** Текущий квартал — период по умолчанию для режима «За период». */
function currentQuarter(): { start: string; end: string } {
  const now = new Date();
  const firstMonth = Math.floor(now.getMonth() / 3) * 3;
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return {
    start: iso(new Date(now.getFullYear(), firstMonth, 1)),
    end: iso(new Date(now.getFullYear(), firstMonth + 3, 0)),
  };
}

export default function TeamDeskPage() {
  useRegisterHelp('Рабочий стол тимлида', teamDeskHelp);
  const [showThresholds, setShowThresholds] = useState(false);
  const [selectedDev, setSelectedDev] = useState<string | null>(null);
  const [flagFilter, setFlagFilter] = useState<FlagCode | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  // Какая строка очереди разложена по задачам: расшифровка живёт до
  // следующего клика, в профиле не сохраняется — это разовый разрез.
  const [queueScope, setQueueScope] = useState<QueueScope>(null);
  // Тимлид пробует все три раскладки и остаётся на удобной — переключать
  // её каждый вход он не должен.
  const [layout, setLayout] = useState<Layout>(
    () => (localStorage.getItem(LAYOUT_KEY) as Layout) || 'cards',
  );
  useEffect(() => localStorage.setItem(LAYOUT_KEY, layout), [layout]);

  // Вся шапка раздела живёт в профиле: тимлид настраивает вид один раз и
  // видит его при следующем заходе с любого компьютера.
  const filterPrefs = useDeskFilter();
  const saveFilter = useSaveDeskFilter();
  // Пока тимлид ничего не трогал, показываем сохранённый в профиле выбор;
  // после первой правки главной становится правка на экране.
  const [picked, setPicked] = useState<DeskFilterPrefs | null>(null);
  const quarter = currentQuarter();
  const prefs: DeskFilterPrefs = {
    teams: [], developers: [], mode: 'open',
    period_start: quarter.start, period_end: quarter.end,
    show_reviewed: false, show_done_subtasks: true, status_counters: [],
    ...(filterPrefs.data ?? {}),
    ...(picked ?? {}),
  };
  const { teams, developers } = prefs;
  const periodStart = prefs.period_start ?? quarter.start;
  const periodEnd = prefs.period_end ?? quarter.end;

  const change = (patch: Partial<DeskFilterPrefs>) => {
    const next = { ...prefs, ...patch };
    setPicked(next);
    saveFilter.mutate(next);
  };

  const settings = useDeskSettings();
  const jiraBaseUrl = useJiraBaseUrl().data?.base_url ?? '';
  const overview = useDeskOverview({
    teams,
    developers,
    mode: prefs.mode,
    periodStart,
    periodEnd,
    showReviewed: prefs.show_reviewed,
    showDoneSubtasks: prefs.show_done_subtasks,
  });
  const data = overview.data;
  const overrunPct = settings.data?.thresholds.overrun_pct ?? 30;
  const wipLimit = settings.data?.thresholds.wip_limit ?? 3;
  const rubberDays = settings.data?.thresholds.rubber_days ?? 5;
  const saveDailyRate = useSaveDailyRate();
  const setDailyRate = (issueId: string, hours: number | null) =>
    saveDailyRate.mutate({ issueId, hours });

  // Список статусов для настройки: те, по которым в срезе есть задачи, плюс
  // ранее выбранные — иначе выбор молча сбрасывался бы на пустом срезе.
  const seenStatuses = new Set<string>(prefs.status_counters);
  (data?.developers ?? []).forEach((dev) =>
    Object.keys(dev.status_counts ?? {}).forEach((s) => seenStatuses.add(s)));
  const statusGroups = settings.data?.status_groups;
  const statusOptions = orderedStatuses(statusGroups, seenStatuses);
  // Только для разрезов по разработчикам: плитки, ведомость, «проблемы вперёд».
  const shownStatuses = prefs.status_counters.length
    ? orderedStatuses(statusGroups, prefs.status_counters)
    : statusOptions;

  // Итог по срезу: задачи разбиты по владельцам, поэтому сумма по людям — это
  // и есть счётчик команды, без задвоений.
  const totalStatusCounts: Record<string, number> = {};
  (data?.developers ?? []).forEach((dev) =>
    Object.entries(dev.status_counts ?? {}).forEach(([status, count]) => {
      totalStatusCounts[status] = (totalStatusCounts[status] ?? 0) + count;
    }));

  const pickStatus = (developerId: string, status: string | null) => {
    setSelectedDev(status ? developerId : null);
    setStatusFilter(status);
  };

  // Клик по строке очереди и по значку замечания на плитке: человек остаётся
  // выбранным и после снятия разреза — иначе экран прыгает обратно на всю команду.
  const pickQueue = (developerId: string, scope: QueueScope) => {
    setSelectedDev(developerId);
    setQueueScope(scope);
  };

  const pickFlag = (developerId: string, flag: FlagCode | null) => {
    setSelectedDev(developerId);
    setFlagFilter(flag);
  };

  const resetFilters = () => {
    setSelectedDev(null);
    setFlagFilter(null);
    setStatusFilter(null);
    setQueueScope(null);
  };

  // Разработчика сняли — фильтр по его статусу тоже снимается, иначе список
  // остался бы урезанным без видимой причины.
  const pickDeveloper = (id: string | null) => {
    setSelectedDev(id);
    if (!id) {
      setStatusFilter(null);
      setQueueScope(null);
    }
  };

  const selectedName = data?.developers.find(
    (dev) => dev.developer_id === selectedDev,
  )?.display_name;

  // Отборы стоят вплотную к таблице задач: влияют они только на неё.
  const filterBars = data && (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <FlagFilterBar
        flagCounts={data.flag_counts}
        value={flagFilter}
        onChange={setFlagFilter}
      />
      <StatusFilterBar
        counts={totalStatusCounts}
        // Полоса — фильтр на весь срез, а не разрез по людям: показываем
        // все статусы среза, иначе выбор счётчиков отнимал бы фильтрацию
        // по остальным статусам.
        statuses={statusOptions}
        statusGroups={statusGroups}
        value={statusFilter}
        // Фильтр на весь срез: выбор конкретного человека снимается.
        onChange={(status) => {
          setSelectedDev(null);
          setStatusFilter(status);
        }}
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
      />
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

      <DeskFilters
        teams={teams}
        onTeamsChange={(value) => change({ teams: value })}
        developers={developers}
        onDevelopersChange={(value) => change({ developers: value })}
        developerRoles={settings.data?.developer_roles ?? ['dev']}
        mode={prefs.mode}
        onModeChange={(value) => change({ mode: value })}
        periodStart={periodStart}
        periodEnd={periodEnd}
        onPeriodChange={(start, end) =>
          change({ period_start: start, period_end: end })}
        showReviewed={prefs.show_reviewed}
        onShowReviewedChange={(value) => change({ show_reviewed: value })}
        showDoneSubtasks={prefs.show_done_subtasks}
        onShowDoneSubtasksChange={(value) => change({ show_done_subtasks: value })}
        onToggleThresholds={() => setShowThresholds((v) => !v)}
      />

      {showThresholds && settings.data && (
        <ThresholdsPanel
          key={JSON.stringify(settings.data.thresholds)}
          settings={settings.data}
          statusOptions={statusOptions}
          statusCounters={prefs.status_counters}
          onStatusCountersChange={(value) => change({ status_counters: value })}
        />
      )}

      <Tabs
        activeKey={layout}
        onChange={(key) => setLayout(key as Layout)}
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
        />
      )}


      {data && (
        <Card size="small" title="Отсутствия">
          <AbsenceStrip employeeIds={data.employee_ids ?? {}} />
        </Card>
      )}
    </Space>
  );
}
