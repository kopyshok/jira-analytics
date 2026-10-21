import { useEffect, useMemo, useState } from 'react';
import { Empty, Spin } from 'antd';
import dayjs from 'dayjs';
import {
  FLAG_LABELS, FLAG_ORDER, roundHours, type DeskIssue,
} from '../../../api/teamDesk';
import { DeskFilters } from '../../../components/teamdesk/DeskFilters';
import { ThresholdsPanel } from '../../../components/teamdesk/ThresholdsPanel';
import { DeveloperTable } from '../../../components/teamdesk/DeveloperTable';
import { GroupedIssues } from '../../../components/teamdesk/GroupedIssues';
import { WorkloadBars } from '../../../components/teamdesk/WorkloadBars';
import { AbsenceStrip } from '../../../components/teamdesk/AbsenceStrip';
import { ActiveFilters } from '../../../components/teamdesk/ActiveFilters';
import { StatusCounters } from '../../../components/teamdesk/StatusCounters';
import { IssueKey, StatusTag } from '../../../components/teamdesk/IssueCells';
import { DailyRateInput } from '../../../components/teamdesk/DailyRateInput';
import { rubberLeft, rubberToQueue } from '../../../components/teamdesk/deskSignals';
import DetailSheet from '../../../components/common/DetailSheet';
import { useAbsences } from '../../../hooks/useAbsences';
import type { DeskLayout, TeamDeskPageState } from '../../../hooks/useTeamDeskPage';
import { PcRow, PcTitle, PModule, PultScreen } from '../ui';
import PultDeveloperCard from './PultDeveloperCard';

const LAYOUTS: { key: DeskLayout; label: string }[] = [
  { key: 'cards', label: 'Светофор' },
  { key: 'table', label: 'Ведомость' },
  { key: 'grouped', label: 'Проблемы вперёд' },
];

/** Резиновые задачи: по каждой — дневная норма (правится) и что из неё уходит в очередь. */
function PultRubber({ rows, jiraBaseUrl, onDailyRate, rubberDays }: {
  rows: DeskIssue[];
  rubberDays: number;
  jiraBaseUrl: string;
  onDailyRate: (issueId: string, hours: number | null) => void;
}) {
  return (
    <section className="pm td-rubber" aria-label="Резиновые задачи">
      <div className="td-rubber-list">
        {rows.map((row) => {
          const left = rubberLeft(row);
          return (
            <div key={row.id} className="td-rubber-item">
              <div className="td-rubber-title">
                <b>{row.developer_name ?? '—'}</b> · <IssueKey issueKey={row.key} jiraBaseUrl={jiraBaseUrl} /> {row.summary}
              </div>
              <div className="td-rubber-status"><StatusTag status={row.status} group={row.status_group} /></div>
              <div className="td-screens">
                <label className="td-screen">
                  <span className="pc-cap">ч/день</span>
                  <DailyRateInput
                    variant="borderless"
                    value={row.daily_rate ?? null}
                    onCommit={(hours) => onDailyRate(row.id, hours)}
                    ariaLabel={`Часов в день: ${row.key}`}
                  />
                </label>
                <div className="td-screen"><span className="pc-cap">оценка</span><b className="num">{row.est_hours == null ? '—' : roundHours(row.est_hours)}</b></div>
                <div className="td-screen"><span className="pc-cap">факт</span><b className="num">{roundHours(row.fact_hours)}</b></div>
                <div className="td-screen"><span className="pc-cap">осталось</span><b className="num">{left == null ? '—' : roundHours(left)}</b></div>
                <div className="td-screen is-dark"><span className="pc-cap">в очередь</span><b className="num">{roundHours(rubberToQueue(row, rubberDays))}</b></div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

type DeskList = 'rubber' | 'wip' | 'absence';

/** Клавиша-счётчик над таблицей: открывает список в панели подробностей; ноль — приглушена
 * и не нажимается, кроме списка, в котором есть что смотреть и при нуле (alwaysOpen). */
function ListKey({ label, count, note, active, onClick, title, alwaysOpen = false }: {
  label: string;
  count: number;
  note?: string | null;
  active: boolean;
  onClick: () => void;
  title?: string;
  alwaysOpen?: boolean;
}) {
  return (
    <button
      type="button"
      className={`td-flag-key td-list-key${active ? ' is-on' : ''}`}
      aria-pressed={active}
      disabled={count === 0 && !alwaysOpen}
      onClick={onClick}
      title={title}
    >
      {label}
      <span className={`p-count ${count === 0 ? 'is-plain' : 'is-key'}`}>{count}</span>
      {note && <span className="td-list-note">{note}</span>}
    </button>
  );
}

/** Границы текущего квартала, «2026-10-01» … «2026-12-31». */
function currentQuarter(): [string, string] {
  const now = dayjs();
  const first = now.month() - (now.month() % 3);
  const start = now.month(first).date(1);
  return [start.format('YYYY-MM-DD'), start.add(2, 'month').endOf('month').format('YYYY-MM-DD')];
}

/**
 * «Рабочий стол тимлида» в обложке «Пульт» (D-desk): панель управления с
 * раскладкой и отборами; модули Светофор · Отборы · Задачи во всю ширину.
 * Резиновые, «в работе одновременно» и отсутствия — счётчики над таблицей,
 * список открывается в панели подробностей. Данные и обработчики — общий хук страницы.
 */
export default function PultTeamDeskLayout({ desk }: { desk: TeamDeskPageState }) {
  const {
    showThresholds, selectedDev, flagFilter, setFlagFilter, statusFilter, queueScope,
    layout, setLayout, filterPrefs, prefs, change, settings, jiraBaseUrl, overview, data,
    overrunPct, wipLimit, rubberDays, setDailyRate,
    statusGroups, statusOptions, shownStatuses, statusBarCounts,
    listProps, pickStatus, pickQueue, pickFlag, resetFilters, pickDeveloper, pickTotalStatus,
    selectedName, filterProps,
  } = desk;

  const panel = (
    <>
      <PcRow style={{ alignItems: 'center' }}>
        <PcTitle
          title="Рабочий стол тимлида"
          sub="Контроль задач в разрезе разработчиков: где стоит, кто не укладывается в оценку, что не разбито на подзадачи."
        />
        <div className="pc-push td-layout-keys" role="tablist" aria-label="Раскладка" data-tour="desk-tabs">
          {LAYOUTS.map((l) => (
            <button
              key={l.key}
              type="button"
              role="tab"
              aria-selected={layout === l.key}
              className={`p-key${layout === l.key ? ' is-on' : ''}`}
              onClick={() => setLayout(l.key)}
            >
              {l.label}
            </button>
          ))}
        </div>
      </PcRow>
      <div data-tour="desk-filters">
        <DeskFilters {...filterProps} variant="panel" />
      </div>
    </>
  );

  const loading = overview.isLoading || filterPrefs.isLoading;
  const flagged = data ? FLAG_ORDER.filter((f) => data.flag_counts[f]) : [];

  // Списки бывшей правой колонки: на странице — счётчики, сам список — в панели (одна за раз).
  const [list, setList] = useState<DeskList | null>(null);
  const toggleList = (next: DeskList) => setList(list === next ? null : next);
  const absences = useAbsences();
  const rubberRows = useMemo(() => (data?.issues ?? []).filter((issue) => issue.daily_rate), [data]);
  const wipTotal = (data?.developers ?? []).reduce((n, d) => n + d.in_progress, 0);
  const wipOver = (data?.developers ?? []).filter((d) => d.in_progress > wipLimit).length;
  const absenceCount = useMemo(() => {
    const ids = new Set(Object.values(data?.employee_ids ?? {}));
    const [from, to] = currentQuarter();
    return (absences.data ?? []).filter((a) => ids.has(a.employee_id) && a.start_date <= to && a.end_date >= from).length;
  }, [absences.data, data]);
  const counts: Record<DeskList, number> = { rubber: rubberRows.length, wip: wipTotal, absence: absenceCount };
  // Список опустел (сменили отбор) — панель закрывается и сама не вернётся.
  // Отсутствия открываются и при нуле: в списке выбирается другой квартал.
  if (list && list !== 'absence' && data && counts[list] === 0) setList(null);
  const shownList = list && data && (list === 'absence' || counts[list] > 0) ? list : null;
  // Рабочая область ужалась под панель — нажатый счётчик остаётся на виду.
  useEffect(() => {
    if (!shownList) return;
    const frame = requestAnimationFrame(() =>
      document.querySelector('.td-list-key.is-on')?.scrollIntoView({ block: 'nearest' }));
    return () => cancelAnimationFrame(frame);
  }, [shownList]);

  const top = data && layout === 'cards' && (
    <PModule title="Светофор" className="td-lights">
      <div className="td-cards">
        {data.developers.map((dev) => {
          const isSelected = selectedDev === dev.developer_id;
          return (
            <PultDeveloperCard
              key={dev.developer_id}
              dev={dev}
              load={data.workload[dev.developer_id]}
              overrunPct={overrunPct}
              selected={isSelected}
              onSelect={() => pickDeveloper(isSelected ? null : dev.developer_id)}
              statuses={shownStatuses}
              statusGroups={statusGroups}
              statusFilter={statusFilter}
              onStatusFilter={(status) => pickStatus(dev.developer_id, status)}
              queueScope={queueScope}
              onQueueFilter={(scope) => pickQueue(dev.developer_id, scope)}
              flagFilter={flagFilter}
              onFlagFilter={(flag) => pickFlag(dev.developer_id, flag)}
            />
          );
        })}
      </div>
    </PModule>
  );

  const summary = data && layout === 'table' && (
    <PModule title="Сводка по разработчикам" className="td-summary">
      <div className="pm-screen td-summary-screen">
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
      </div>
    </PModule>
  );

  const filters = data && (
    <section className="pm td-filters-module" data-tour="desk-flags" aria-label="Отборы и статусы">
      <div className="td-filters-line">
        <span className="pm-cap td-filters-cap">Отборы</span>
        <div className="td-flagbar">
          <span className="pc-cap">Требует внимания</span>
          {flagged.length === 0 && <span className="td-note">Замечаний нет</span>}
          {flagged.map((flag) => {
            const active = flagFilter === flag;
            return (
              <button
                key={flag}
                type="button"
                className={`td-flag-key${active ? ' is-on' : ''}`}
                aria-pressed={active}
                onClick={() => setFlagFilter(active ? null : flag)}
              >
                {FLAG_LABELS[flag]}
                <span className={`p-count ${flag === 'over' ? 'is-red' : 'is-amber'}`}>{data.flag_counts[flag]}</span>
              </button>
            );
          })}
        </div>
        <span className="td-sep" aria-hidden="true" />
        <div className="td-statusbar">
          <span className="pc-cap">Задачи по статусам</span>
          {statusOptions.some((s) => statusBarCounts[s]) ? (
            <StatusCounters
              counts={statusBarCounts}
              statuses={statusOptions}
              statusGroups={statusGroups}
              selected={statusFilter}
              onSelect={pickTotalStatus}
            />
          ) : <span className="td-note">Задач нет</span>}
        </div>
      </div>
      <ActiveFilters
        developerName={selectedName}
        flag={flagFilter}
        status={statusFilter}
        queueScope={queueScope}
        onReset={resetFilters}
      />
    </section>
  );

  // Счётчики бывшей правой колонки — в строке над таблицей задач.
  const lists = data && (
    <div className="td-listbar" role="group" aria-label="Списки стола">
      <span className="pc-cap">Списки</span>
      <ListKey
        label="Резиновые"
        count={counts.rubber}
        active={shownList === 'rubber'}
        onClick={() => toggleList('rubber')}
        title="Задачи с дневной нормой: что из неё уходит в очередь"
      />
      <ListKey
        label="В работе одновременно"
        count={counts.wip}
        note={wipOver > 0 ? `сверх лимита у ${wipOver}` : null}
        active={shownList === 'wip'}
        onClick={() => toggleList('wip')}
        title={`Задач в работе сейчас; лимит — ${wipLimit} на человека`}
      />
      <ListKey
        label="Отсутствия"
        count={counts.absence}
        active={shownList === 'absence'}
        onClick={() => toggleList('absence')}
        title="Отсутствия людей стола в текущем квартале; в списке можно выбрать другой квартал"
        alwaysOpen
      />
    </div>
  );

  const tasks = data && (
    <div className="td-tasks" data-tour="desk-issues">
      {layout === 'grouped' ? (
        <GroupedIssues
          docked
          title={<span className="pm-cap">Задачи по разработчикам</span>}
          developers={data.developers}
          issues={data.issues}
          overrunPct={overrunPct}
          jiraBaseUrl={jiraBaseUrl}
          scale="centered"
          flagFilter={flagFilter}
          statusFilter={statusFilter}
          onlyDeveloper={selectedDev}
          queueScope={queueScope}
          onDailyRate={setDailyRate}
          statuses={shownStatuses}
          statusGroups={statusGroups}
          onStatusFilter={pickStatus}
          headExtra={lists}
          {...listProps}
        />
      ) : (
        <GroupedIssues
          docked
          title={<span className="pm-cap">Задачи</span>}
          developers={data.developers}
          issues={data.issues}
          overrunPct={overrunPct}
          jiraBaseUrl={jiraBaseUrl}
          onlyDeveloper={selectedDev}
          flagFilter={flagFilter}
          statusFilter={statusFilter}
          queueScope={queueScope}
          onDailyRate={setDailyRate}
          headExtra={lists}
          {...listProps}
        />
      )}
    </div>
  );

  return (
    <PultScreen panel={panel} bodyClassName="td-pult">
      {showThresholds && settings.data && (
        <section className="pm td-thresholds" aria-label="Настройки вида">
          <ThresholdsPanel
            key={JSON.stringify([settings.data.thresholds, settings.data.disabled_flags])}
            settings={settings.data}
            statusOptions={statusOptions}
            statusCounters={prefs.status_counters}
            onStatusCountersChange={(value) => change({ status_counters: value })}
          />
        </section>
      )}

      {loading && <div className="pm-empty"><Spin /></div>}
      {!loading && !data && (
        <div className="pm td-empty"><Empty description="Выберите команды или добавьте разработчиков" /></div>
      )}

      {data && (
        <>
          {top}
          {summary}
          {filters}
          {tasks}
        </>
      )}

      <DetailSheet
        open={!!shownList}
        onClose={() => setList(null)}
        title={shownList === 'rubber' ? 'Резиновые задачи' : shownList === 'wip' ? 'Задач в работе одновременно' : 'Отсутствия'}
        subtitle={shownList === 'rubber'
          ? `в очередь идёт норма за ${rubberDays} дн, но не больше остатка`
          : shownList === 'wip'
            ? `задачи в работе у каждого сейчас; лимит на человека — ${wipLimit}`
            : 'люди стола по дням квартала'}
        ariaLabel="Списки стола тимлида"
        className="td-sheet"
      >
        {data && shownList === 'rubber' && (
          <PultRubber rows={rubberRows} rubberDays={rubberDays} jiraBaseUrl={jiraBaseUrl} onDailyRate={setDailyRate} />
        )}
        {data && shownList === 'wip' && (
          <section className="pm td-wip" aria-label="Задач в работе одновременно">
            <WorkloadBars developers={data.developers} workload={data.workload} limit={wipLimit} />
          </section>
        )}
        {data && shownList === 'absence' && (
          <section className="pm td-absence" aria-label="Отсутствия">
            <AbsenceStrip employeeIds={data.employee_ids ?? {}} />
          </section>
        )}
      </DetailSheet>
    </PultScreen>
  );
}
