import { useEffect, useMemo, useState } from 'react';
import { Button, Empty, Popover, Segmented, Spin } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
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
import DetailSheet from '../../../components/common/DetailSheet';
import { useAbsences } from '../../../hooks/useAbsences';
import DeskDeveloperCards from '../components/DeskDeveloperCards';

type DeskList = 'rubber' | 'wip' | 'absence';

/** Границы текущего квартала: «2026-10-01» … «2026-12-31». */
function currentQuarter(): [string, string] {
  const now = dayjs();
  const start = now.month(now.month() - (now.month() % 3)).date(1);
  return [start.format('YYYY-MM-DD'), start.add(2, 'month').endOf('month').format('YYYY-MM-DD')];
}

/** Счётчик списка над таблицей: открывает список в панели подробностей; ноль — приглушён и не нажимается. */
function ListChip({ label, count, note, active, onClick, title }: {
  label: string;
  count: number;
  note?: string | null;
  active: boolean;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      className={`tdc-chip tdc-list-chip${active ? ' is-active' : ''}`}
      aria-pressed={active}
      disabled={count === 0}
      onClick={onClick}
      title={title}
    >
      {label} <b>{count}</b>
      {note && <span className="tdc-list-note">{note}</span>}
    </button>
  );
}

/**
 * «Рабочий стол тимлида» в скине «Тёплая» (макет C-desk): заголовок и
 * раскладки справа, две строки фильтров, плитки разработчиков в ряд (или
 * ведомость), под ними — отборы и таблица задач во всю ширину. Резиновые
 * задачи, задачи в работе одновременно и отсутствия — счётчики в полосе
 * отборов; сам список открывается в панели подробностей. Страница помещается
 * в экран, длинные части прокручиваются внутри своих блоков. Данные и
 * обработчики — общие с раскладкой Aurora (useTeamDeskPage).
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
  const grouped = layout === 'grouped';

  // Списки бывшей правой колонки: на странице — счётчики, сам список — в панели (одна за раз).
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
  // Как у Aurora: в «Проблемах вперёд» полос загрузки нет.
  const counts: Record<DeskList, number> = { rubber: rubberCount, wip: grouped ? 0 : wipTotal, absence: absenceCount };
  // Список опустел (сменили отбор или раскладку) — панель закрывается и сама не вернётся.
  if (list && data && counts[list] === 0) setList(null);
  const shownList = list && data && counts[list] > 0 ? list : null;
  // Рабочая область ужалась под панель — нажатый счётчик остаётся на виду.
  useEffect(() => {
    if (!shownList) return;
    const frame = requestAnimationFrame(() =>
      document.querySelector('.tdc-list-chip.is-active')?.scrollIntoView({ block: 'nearest' }));
    return () => cancelAnimationFrame(frame);
  }, [shownList]);

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
      <div className="tdc-bar" role="group" aria-label="Списки">
        <span className="tdc-bar-label">Списки</span>
        <ListChip
          label="Резиновые"
          count={counts.rubber}
          active={shownList === 'rubber'}
          onClick={() => toggleList('rubber')}
          title={counts.rubber
            ? 'Задачи с дневной нормой: что из неё уходит в очередь'
            : 'Резиновых задач нет — норма в день задаётся в колонке DevForDay'}
        />
        {!grouped && (
          <ListChip
            label="В работе одновременно"
            count={counts.wip}
            note={wipOver > 0 ? `сверх лимита у ${wipOver}` : null}
            active={shownList === 'wip'}
            onClick={() => toggleList('wip')}
            title={`Задач в работе сейчас у людей стола; лимит — ${wipLimit} на человека`}
          />
        )}
        <ListChip
          label="Отсутствия"
          count={counts.absence}
          active={shownList === 'absence'}
          onClick={() => toggleList('absence')}
          title="Отсутствия людей стола в текущем квартале"
        />
      </div>
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
          {filterBars}
          {issues}
        </div>
      )}

      <DetailSheet
        open={!!shownList}
        onClose={() => setList(null)}
        title={shownList === 'rubber'
          ? `Резиновые задачи · ${counts.rubber}`
          : shownList === 'wip' ? 'Задач в работе одновременно' : 'Отсутствия'}
        subtitle={shownList === 'rubber'
          ? `в очередь идёт норма за ${rubberDays} дн, но не больше остатка`
          : shownList === 'wip'
            ? `задачи в работе у каждого сейчас; лимит на человека — ${wipLimit}`
            : 'люди стола по дням квартала'}
        ariaLabel="Списки стола тимлида"
        className="tdc-sheet"
      >
        {data && shownList === 'rubber' && (
          <div className="tdc-sheet-rubber">
            <RubberTasks
              compact
              issues={data.issues}
              rubberDays={rubberDays}
              jiraBaseUrl={jiraBaseUrl}
              onDailyRate={setDailyRate}
            />
          </div>
        )}
        {data && shownList === 'wip' && (
          <div className="tdc-sheet-wip">
            <WorkloadBars
              compact
              developers={data.developers}
              workload={data.workload}
              limit={wipLimit}
            />
          </div>
        )}
        {data && shownList === 'absence' && (
          <div className="tdc-sheet-abs">
            <AbsenceStrip employeeIds={data.employee_ids ?? {}} />
          </div>
        )}
      </DetailSheet>
    </div>
  );
}
