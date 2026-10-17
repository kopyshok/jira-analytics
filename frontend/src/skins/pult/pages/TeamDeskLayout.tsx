import { Empty, InputNumber, Spin } from 'antd';
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
import { rubberLeft, rubberToQueue } from '../../../components/teamdesk/deskSignals';
import type { DeskLayout, TeamDeskPageState } from '../../../hooks/useTeamDeskPage';
import { PcRow, PcTitle, PModule, PultScreen } from '../ui';
import PultDeveloperCard from './PultDeveloperCard';

const LAYOUTS: { key: DeskLayout; label: string }[] = [
  { key: 'cards', label: 'Светофор' },
  { key: 'table', label: 'Ведомость' },
  { key: 'grouped', label: 'Проблемы вперёд' },
];

/** Резиновые задачи: по каждой — дневная норма (правится) и что из неё уходит в очередь. */
function PultRubber({ issues, rubberDays, jiraBaseUrl, onDailyRate }: {
  issues: DeskIssue[];
  rubberDays: number;
  jiraBaseUrl: string;
  onDailyRate: (issueId: string, hours: number | null) => void;
}) {
  const rows = issues.filter((issue) => issue.daily_rate);
  return (
    <PModule
      title="Резиновые задачи"
      className="td-rubber"
      extra={<span className="pm-push pc-count is-small">{rows.length}</span>}
    >
      <p className="td-note">в очередь идёт норма за {rubberDays} дн, но не больше остатка</p>
      {rows.length === 0 && <div className="td-note">Резиновых задач в срезе нет</div>}
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
                  <InputNumber
                    size="small"
                    variant="borderless"
                    min={0}
                    max={24}
                    step={0.5}
                    value={row.daily_rate ?? null}
                    onChange={(v) => onDailyRate(row.id, v == null ? null : Number(v))}
                    aria-label={`Часов в день: ${row.key}`}
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
    </PModule>
  );
}

/**
 * «Рабочий стол тимлида» в обложке «Пульт» (D-desk): панель управления с
 * раскладкой и отборами; модули Светофор · Отборы · Задачи · Резиновые ·
 * Одновременно · Отсутствия. Данные и обработчики — общий хук страницы.
 */
export default function PultTeamDeskLayout({ desk }: { desk: TeamDeskPageState }) {
  const {
    showThresholds, selectedDev, flagFilter, setFlagFilter, statusFilter, queueScope,
    layout, setLayout, filterPrefs, prefs, change, settings, jiraBaseUrl, overview, data,
    overrunPct, wipLimit, rubberDays, setDailyRate,
    statusGroups, statusOptions, shownStatuses, totalStatusCounts,
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
          {statusOptions.some((s) => totalStatusCounts[s]) ? (
            <StatusCounters
              counts={totalStatusCounts}
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
          <div className="td-bottom">
            <div className="td-main">
              {filters}
              {tasks}
            </div>
            <div className="td-side">
              <PultRubber
                issues={data.issues}
                rubberDays={rubberDays}
                jiraBaseUrl={jiraBaseUrl}
                onDailyRate={setDailyRate}
              />
              <PModule
                title="Задач в работе одновременно"
                className="td-wip"
                extra={<span className="pm-push num td-note">лимит {wipLimit}</span>}
              >
                <WorkloadBars
                  developers={data.developers}
                  workload={data.workload}
                  limit={wipLimit}
                />
              </PModule>
              <PModule title="Отсутствия" className="td-absence">
                <div className="td-absence-body">
                  <AbsenceStrip employeeIds={data.employee_ids ?? {}} compact />
                </div>
              </PModule>
            </div>
          </div>
        </>
      )}
    </PultScreen>
  );
}
