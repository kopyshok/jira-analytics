import { useMemo, useState } from 'react';
import { Empty, Spin } from 'antd';
import dayjs from 'dayjs';
import type { DeskDeveloper, DeskIssue, DeskWorkload } from '../../../api/teamDesk';
import type { TeamDeskPageModel, DeskLayout } from '../../../hooks/useTeamDeskPage';
import { useAbsences } from '../../../hooks/useAbsences';
import DetailSheet from '../../../components/common/DetailSheet';
import { useDetailSheetWidth } from '../../../components/common/detailSheetWidth';
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
import { useKeepInView } from '../useKeepInView';
import './teamDesk.css';

/** Колонки списка задач под ширину зоны данных (макет: видно до «Дней», дальше — прокрутка в блоке). */
const COLUMN_WIDTHS: Record<string, number> = {
  task: 240, developer: 120, status: 112, sprint: 92, release: 68, est: 58,
  daily_rate: 74, fact: 46, left: 70, scale: 104, days: 46, flags: 120,
};

const TABS: { key: DeskLayout; num: string; label: string }[] = [
  { key: 'cards', num: '1.1', label: 'Светофор' },
  { key: 'table', num: '1.2', label: 'Ведомость' },
  { key: 'grouped', num: '1.3', label: 'Проблемы вперёд' },
];

type DeskList = 'rubber' | 'wip' | 'absence';

const LISTS: Record<DeskList, { num: string; title: string }> = {
  rubber: { num: '1.5', title: 'Резиновые задачи' },
  wip: { num: '1.6', title: 'Задач в работе одновременно' },
  absence: { num: '1.7', title: 'Отсутствия' },
};

/**
 * Счётчик над таблицей: открывает список в панели подробностей; ноль — приглушён и не нажимается.
 * openAtZero — ноль приглушён, но список открывается (отсутствия: в панели можно выбрать другой квартал).
 */
function ListKey({ num, label, count, note, active, onClick, title, openAtZero = false }: {
  num: string;
  label: string;
  count: number;
  note?: string | null;
  active: boolean;
  onClick: () => void;
  title?: string;
  openAtZero?: boolean;
}) {
  return (
    <button
      type="button"
      className={`sw-desk-list${active ? ' is-active' : ''}${count === 0 && openAtZero ? ' is-zero' : ''}`}
      aria-pressed={active}
      disabled={count === 0 && !openAtZero}
      onClick={onClick}
      title={title}
    >
      <span className="sw-desk-list-num">{num}</span>
      {label}
      <b>{count}</b>
      {note && <span className="sw-desk-list-note">{note}</span>}
    </button>
  );
}

/** Список в панели: на широкой — таблицей и теплокартой по дням, на узкой — строками и неделями. */
function DeskListBody({ list, issues, developers, workload, wipLimit, employeeIds, rubberDays, jiraBaseUrl, onDailyRate }: {
  list: DeskList;
  issues: DeskIssue[];
  developers: DeskDeveloper[];
  workload: Record<string, DeskWorkload>;
  wipLimit: number;
  employeeIds: Record<string, string>;
  rubberDays: number;
  jiraBaseUrl: string;
  onDailyRate: (issueId: string, hours: number | null) => void;
}) {
  const wide = useDetailSheetWidth() >= 960;
  if (list === 'rubber') {
    return (
      <RubberTasks
        compact={!wide}
        issues={issues}
        rubberDays={rubberDays}
        jiraBaseUrl={jiraBaseUrl}
        onDailyRate={onDailyRate}
      />
    );
  }
  if (list === 'wip') {
    return (
      <section className="desk-wip-block">
        <WorkloadBars developers={developers} workload={workload} limit={wipLimit} />
      </section>
    );
  }
  return <AbsenceStrip compact={!wide} employeeIds={employeeIds} />;
}

/** Границы текущего квартала, «2026-10-01» … «2026-12-31». */
function currentQuarter(): [string, string] {
  const now = dayjs();
  const start = now.month(now.month() - (now.month() % 3)).date(1);
  return [start.format('YYYY-MM-DD'), start.add(2, 'month').endOf('month').format('YYYY-MM-DD')];
}

/**
 * «Рабочий стол тимлида» в обложке «Швейцарская»: паспорт (цифры среза и
 * отбор столбиком), справа вкладки-разрезы, плитки людей и список задач во
 * всю ширину. Резиновые задачи, «в работе одновременно» и отсутствия —
 * счётчики над таблицей, сам список открывается в панели подробностей.
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

  // Списки бывшей правой колонки: на странице — счётчики, сам список — в панели (одна за раз).
  // «В работе одновременно» в разрезе «Проблемы вперёд» не показывался и сейчас не показывается.
  const showWip = layout !== 'grouped';
  const [list, setList] = useState<DeskList | null>(null);
  const toggleList = (next: DeskList) => setList(list === next ? null : next);
  const absences = useAbsences();
  const rubberCount = useMemo(() => (data?.issues ?? []).filter((issue) => issue.daily_rate).length, [data]);
  const wipTotal = (data?.developers ?? []).reduce((n, d) => n + d.in_progress, 0);
  const wipOver = (data?.developers ?? []).filter((d) => d.in_progress > wipLimit).length;
  const absenceCount = useMemo(() => {
    const ids = new Set(Object.values(data?.employee_ids ?? {}));
    const [from, to] = currentQuarter();
    return (absences.data ?? []).filter((a) => ids.has(a.employee_id) && a.start_date <= to && a.end_date >= from).length;
  }, [absences.data, data]);
  const counts: Record<DeskList, number> = { rubber: rubberCount, wip: showWip ? wipTotal : 0, absence: absenceCount };
  // Отсутствия открываются и при нуле в текущем квартале (в панели — выбор квартала), если на столе есть люди.
  const hasPeople = Object.keys(data?.employee_ids ?? {}).length > 0;
  const canOpen = (l: DeskList) => counts[l] > 0 || (l === 'absence' && hasPeople);
  // Список опустел (сменили отбор или разрез) — панель закрывается и сама не вернётся.
  if (list && data && !canOpen(list)) setList(null);
  const shownList = list && data && canOpen(list) ? list : null;
  // Рабочая область ужалась под панель — нажатый счётчик остаётся на виду.
  useKeepInView(shownList, '.sw-desk-list.is-active');

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
        // «Недобор / перебор» в разрезе «Проблемы вперёд» — шкала в обе стороны, ей нужно шире.
        defaultWidths={layout === 'grouped' ? { ...COLUMN_WIDTHS, scale: 150 } : COLUMN_WIDTHS}
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
            caption={`Перерасход > ${overrunPct}%`}
            title="Задач среза, где факт превысил оценку больше порога из настроек стола"
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
              {/* Списки бывшей правой колонки — счётчиками; сам список — в панели подробностей */}
              <div className="sw-desk-lists" role="group" aria-label="Списки стола">
                <span className="sw-desk-lists-label">Списки</span>
                <ListKey
                  num="1.5"
                  label="Резиновые"
                  count={counts.rubber}
                  active={shownList === 'rubber'}
                  onClick={() => toggleList('rubber')}
                  title="Задачи с дневной нормой: что из неё уходит в очередь"
                />
                {showWip && (
                  <ListKey
                    num="1.6"
                    label="В работе одновременно"
                    count={counts.wip}
                    note={wipOver > 0 ? `сверх лимита у ${wipOver}` : null}
                    active={shownList === 'wip'}
                    onClick={() => toggleList('wip')}
                    title={`Задач в работе сейчас; лимит — ${wipLimit} на человека`}
                  />
                )}
                <ListKey
                  num="1.7"
                  label="Отсутствия"
                  count={counts.absence}
                  active={shownList === 'absence'}
                  onClick={() => toggleList('absence')}
                  title="Отсутствия людей стола в текущем квартале; в панели — любой квартал"
                  openAtZero={hasPeople}
                />
              </div>
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
        )}
      </SwissData>

      <DetailSheet
        open={!!shownList}
        onClose={() => setList(null)}
        title={<><span className="sw-sheet-num">{shownList ? LISTS[shownList].num : ''}</span>{shownList ? LISTS[shownList].title : ''}</>}
        subtitle={shownList === 'rubber'
          ? `в очередь идёт норма за ${rubberDays} дн, но не больше остатка; дневную норму можно поправить прямо здесь`
          : shownList === 'wip'
            ? `задачи в работе у каждого сейчас; лимит на человека — ${wipLimit}`
            : 'люди стола по дням квартала'}
        ariaLabel="Списки стола тимлида"
        className="sw-desk-sheet"
      >
        {data && shownList && (
          <DeskListBody
            list={shownList}
            issues={data.issues}
            developers={data.developers}
            workload={data.workload}
            wipLimit={wipLimit}
            employeeIds={data.employee_ids ?? {}}
            rubberDays={rubberDays}
            jiraBaseUrl={jiraBaseUrl}
            onDailyRate={setDailyRate}
          />
        )}
      </DetailSheet>
    </SwissPage>
  );
}
