import { useEffect, useState } from 'react';
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
import { useAbsences } from '../../../hooks/useAbsences';
import DetailSheet from '../../../components/common/DetailSheet';
import { useDetailSheetWidth } from '../../../components/common/detailSheetWidth';
import type { DeskOverview } from '../../../api/teamDesk';
import ZonesBand, { BandTabs } from '../ZonesBand';
import { DeskDevCards } from './desk/DeskDevCards';
import { DeskAttention } from './desk/DeskAttention';

const SUBTITLE = 'Контроль задач в разрезе разработчиков: где стоит, кто не укладывается в оценку, что не разбито на подзадачи.';

type DeskSheet = 'rubber' | 'wip' | 'absence';

type QuarterRef = { year: number; quarter: number };

/** Текущий квартал. */
function currentQuarter(): QuarterRef {
  const now = new Date();
  return { year: now.getFullYear(), quarter: Math.floor(now.getMonth() / 3) + 1 };
}

/** Первый и последний день квартала, ГГГГ-ММ-ДД. */
function quarterBounds({ year, quarter }: QuarterRef): [string, string] {
  const m = (quarter - 1) * 3;
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return [iso(new Date(year, m, 1)), iso(new Date(year, m + 3, 0))];
}

/** Счётчик списка: щелчок открывает панель, ноль — приглушён и не нажимается,
 * кроме списка, в котором есть что смотреть и при нуле (alwaysOpen). */
function SheetCounter({ label, count, active, extra, onClick, alwaysOpen = false }: {
  label: string; count: number; active: boolean; extra?: string; onClick: () => void; alwaysOpen?: boolean;
}) {
  return (
    <button
      type="button"
      className={`dz-sheet-counter${active ? ' is-active' : ''}${count === 0 ? ' is-zero' : ''}`}
      disabled={count === 0 && !alwaysOpen}
      aria-pressed={active}
      onClick={onClick}
    >
      {label}<b>{count}</b>
      {extra && <span className="dz-sheet-counter-extra">{extra}</span>}
    </button>
  );
}

/** Список в панели: широкая — таблица и теплокарта по дням, узкая — карточки и недели. */
function DeskSheetBody({ kind, data, rubberDays, wipLimit, jiraBaseUrl, onDailyRate, absencePeriod, onAbsencePeriod }: {
  kind: DeskSheet;
  data: DeskOverview;
  rubberDays: number;
  wipLimit: number;
  jiraBaseUrl?: string;
  onDailyRate: (issueId: string, hours: number | null) => void;
  absencePeriod: QuarterRef;
  onAbsencePeriod: (period: QuarterRef) => void;
}) {
  const width = useDetailSheetWidth();
  if (kind === 'rubber') {
    return (
      <div className="dz-sheet-body">
        <RubberTasks
          bare
          compact={width < 1180}
          issues={data.issues}
          rubberDays={rubberDays}
          jiraBaseUrl={jiraBaseUrl}
          onDailyRate={onDailyRate}
        />
      </div>
    );
  }
  if (kind === 'wip') {
    return (
      <div className="dz-sheet-body dz-wip">
        <WorkloadBars developers={data.developers} workload={data.workload ?? {}} limit={wipLimit} />
      </div>
    );
  }
  return (
    <div className="dz-sheet-body">
      <AbsenceStrip
        compact={width < 900}
        employeeIds={data.employee_ids ?? {}}
        period={absencePeriod}
        onPeriodChange={onAbsencePeriod}
      />
    </div>
  );
}

/**
 * «Рабочий стол тимлида» в скине «Цветовые зоны»: отборы и раскладки — в
 * полосе зоны; в теле лента плиток, под ней отборы и таблица задач во всю
 * ширину. Резиновые задачи, задачи в работе и отсутствия — счётчиками над
 * таблицей; щелчок открывает список в панели подробностей. Экран — в высоту окна.
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
  const absences = useAbsences();
  const [sheet, setSheet] = useState<DeskSheet | null>(null);
  // «В работе одновременно» в раскладке «Проблемы вперёд» не показывается — как и прежде.
  const showWip = layout !== 'grouped';
  const openSheet = sheet === 'wip' && !showWip ? null : sheet;
  const toggleSheet = (kind: DeskSheet) => setSheet((cur) => (cur === kind ? null : kind));
  // Панель ужала страницу — счётчики остаются на виду: из них открывается другой список.
  // Лист снизу оставляет мало высоты: счётчики — к верху, под ними начало таблицы задач.
  useEffect(() => {
    if (!openSheet) return;
    const bottom = document.documentElement.dataset.detailSheet === 'bottom';
    document.querySelector('.dz-sheet-counter.is-active')?.scrollIntoView({ block: bottom ? 'start' : 'nearest' });
  }, [openSheet]);

  const rubberCount = data ? data.issues.filter((i) => i.daily_rate).length : 0;
  const busyCount = data ? data.developers.filter((d) => d.in_progress > 0).length : 0;
  const overLimit = data ? data.developers.filter((d) => d.in_progress > wipLimit).length : 0;
  const deskPeople = new Set(Object.values(data?.employee_ids ?? {}));
  const absentIn = (q: QuarterRef) => {
    const [qStart, qEnd] = quarterBounds(q);
    return new Set(
      (absences.data ?? [])
        .filter((a) => deskPeople.has(a.employee_id) && a.start_date <= qEnd && a.end_date >= qStart)
        .map((a) => a.employee_id),
    ).size;
  };
  // Счётчик — текущий квартал; подпись панели — тот квартал, что выбран в панели.
  const nowQuarter = currentQuarter();
  const absentCount = absentIn(nowQuarter);
  const [absencePeriod, setAbsencePeriod] = useState<QuarterRef>(nowQuarter);
  const shownIsNow = absencePeriod.year === nowQuarter.year && absencePeriod.quarter === nowQuarter.quarter;
  const absenceWhen = `${shownIsNow ? 'в текущем квартале' : 'в квартале'} Q${absencePeriod.quarter} ${absencePeriod.year}`;
  const sheetTitle: Record<DeskSheet, string> = {
    rubber: `Резиновые задачи · ${rubberCount}`,
    wip: `Задач в работе одновременно · лимит ${wipLimit}`,
    absence: 'Отсутствия',
  };
  const sheetSubtitle: Record<DeskSheet, string> = {
    rubber: `в очередь идёт норма за ${rubberDays} дн, но не больше остатка`,
    wip: overLimit > 0 ? `сверх лимита: ${overLimit} чел.` : 'все в пределах лимита',
    absence: `${absenceWhen} отсутствуют: ${absentIn(absencePeriod)} чел.`,
  };

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
              panels={(
                <div className="dz-attention-row" role="group" aria-label="Списки в панели подробностей">
                  <span className="dz-attention-label">Списки</span>
                  <SheetCounter
                    label="Резиновые"
                    count={rubberCount}
                    active={openSheet === 'rubber'}
                    onClick={() => toggleSheet('rubber')}
                  />
                  {showWip && (
                    <SheetCounter
                      label="В работе одновременно"
                      count={busyCount}
                      extra={overLimit > 0 ? `${overLimit} сверх лимита` : undefined}
                      active={openSheet === 'wip'}
                      onClick={() => toggleSheet('wip')}
                    />
                  )}
                  <SheetCounter
                    label="Отсутствия"
                    count={absentCount}
                    active={openSheet === 'absence'}
                    onClick={() => toggleSheet('absence')}
                    alwaysOpen
                  />
                </div>
              )}
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
        </div>
      )}
      {data && openSheet && (
        <DetailSheet
          open
          onClose={() => setSheet(null)}
          ariaLabel={sheetTitle[openSheet]}
          className="dz-sheet"
          title={sheetTitle[openSheet]}
          subtitle={sheetSubtitle[openSheet]}
        >
          <DeskSheetBody
            kind={openSheet}
            data={data}
            rubberDays={rubberDays}
            wipLimit={wipLimit}
            jiraBaseUrl={jiraBaseUrl}
            onDailyRate={setDailyRate}
            absencePeriod={absencePeriod}
            onAbsencePeriod={setAbsencePeriod}
          />
        </DetailSheet>
      )}
    </div>
  );
}
