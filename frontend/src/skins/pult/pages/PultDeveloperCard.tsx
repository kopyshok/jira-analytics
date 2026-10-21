import { Tooltip } from 'antd';
import {
  FLAG_LABELS, FLAG_ORDER, roundHours,
  type DeskDeveloper, type DeskWorkload, type FlagCode,
} from '../../../api/teamDesk';
import { StatusCounters } from '../../../components/teamdesk/StatusCounters';
import { accuracyLevel, developerSeverity } from '../../../components/teamdesk/deskSignals';
import type { QueueScope } from '../../../components/teamdesk/queueFilter';
import { PULT_SIGNAL } from '../palette';
import { plural } from '../../../utils/plural';

function initials(name: string | null): string {
  if (!name) return '?';
  const parts = name.split(' ');
  return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase();
}

const ACCURACY_DOT = { bad: PULT_SIGNAL.red, warn: PULT_SIGNAL.amber, good: PULT_SIGNAL.green } as const;

interface Props {
  dev: DeskDeveloper;
  load?: DeskWorkload;
  overrunPct: number;
  selected: boolean;
  onSelect: () => void;
  statuses: string[];
  statusGroups?: Record<string, string[]>;
  statusFilter: string | null;
  onStatusFilter: (status: string | null) => void;
  queueScope: QueueScope;
  onQueueFilter: (scope: QueueScope) => void;
  flagFilter: FlagCode | null;
  onFlagFilter: (flag: FlagCode | null) => void;
}

/** Плитка разработчика «Светофора» в виде прибора: данные и клики — те же, что в Aurora. */
export default function PultDeveloperCard({
  dev, load, overrunPct, selected, onSelect,
  statuses, statusGroups, statusFilter, onStatusFilter,
  queueScope, onQueueFilter, flagFilter, onFlagFilter,
}: Props) {
  const severity = developerSeverity(dev);
  const badge = severity === 2
    ? { text: 'Перерасход', cls: 'is-red' }
    : dev.flag_counts.decomp
      ? { text: 'Без декомпозиции', cls: 'is-amber' }
      : dev.flag_counts.stale
        ? { text: 'Зависла', cls: 'is-amber' }
        : null;
  const est = dev.est_hours || 0;
  const fact = dev.fact_hours;
  const max = Math.max(est, fact, 0.0001);
  const ratio = est > 0 ? fact / est : 0;
  const over = est > 0 && ratio > 1 + overrunPct / 100;
  const level = accuracyLevel(dev.accuracy);
  const flags = FLAG_ORDER.filter((f) => dev.flag_counts[f]);

  const queueLine = (label: string, scope: 'all' | 'assigned', hours: number, days: number | null, withoutEstimate: number) => {
    const active = selected && queueScope === scope;
    return (
      <button
        type="button"
        className={`td-queue${active ? ' is-active' : ''}`}
        aria-pressed={active}
        onClick={(e) => {
          e.stopPropagation();
          onQueueFilter(active ? null : scope);
        }}
      >
        <span>{label}</span>
        <span className="num">
          {roundHours(hours)} ч{days != null ? ` ≈ ${days} дн` : ' · нет свободных дней'}
          {withoutEstimate > 0 ? ` · ещё ${withoutEstimate} без оценки` : ''}
        </span>
      </button>
    );
  };

  return (
    <article
      className={`td-card${selected ? ' is-selected' : ''}`}
      onClick={onSelect}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onSelect();
        }
      }}
      aria-pressed={selected}
    >
      <div className="td-card-head">
        <span className="td-ini num">{initials(dev.display_name)}</span>
        <span className="td-name">{dev.display_name ?? 'Без имени'}</span>
        {dev.team && <span className="pc-cap td-team" title={dev.team}>{dev.team}</span>}
        {badge && <span className={`td-badge ${badge.cls}`}>{badge.text.toUpperCase()}</span>}
      </div>

      <div className="td-card-count">
        <span className="td-big num">{dev.total_issues}</span>
        <span className="pc-cap td-big-cap">{plural(dev.total_issues, 'задача', 'задачи', 'задач')} всего</span>
        <span className="td-split">
          <span><i className="p-dot" style={{ background: PULT_SIGNAL.blue }} /><b className="num">{dev.in_dev}</b> у него</span>
          <span><i className="p-dot" style={{ background: PULT_SIGNAL.amber }} /><b className="num">{dev.waiting}</b> {plural(dev.waiting, 'ждёт', 'ждут', 'ждут')} не его</span>
          <span><i className="p-dot" style={{ background: PULT_SIGNAL.grey }} /><b className="num">{dev.todo}</b> {plural(dev.todo, 'не начата', 'не начаты', 'не начаты')}</span>
        </span>
      </div>

      <div className="td-card-hours">
        <span className="pc-cap">Факт / оценка, ч</span>
        <b className="num">{roundHours(fact)} / {est ? roundHours(est) : '—'}</b>
        <Tooltip title={`Факт ${roundHours(fact)} ч из ${est ? roundHours(est) : '—'} ч`}>
          <span className="td-meter">
            <i className={over ? 'is-over' : ''} style={{ width: `${(fact / max) * 100}%` }} />
            {est > 0 && <u style={{ left: `${(est / max) * 100}%` }} />}
          </span>
        </Tooltip>
        <span className="pc-cap">Точность</span>
        <b className="num td-acc">
          {level && <i className="p-dot" style={{ background: ACCURACY_DOT[level] }} />}
          {dev.accuracy == null ? '—' : `×${dev.accuracy.toFixed(2)}`}
        </b>
      </div>

      {load && (
        <div className="td-queues">
          {queueLine('Очередь', 'all', load.queue_hours, load.queue_days, load.without_estimate)}
          {queueLine('К выполнению', 'assigned', load.assigned_hours, load.assigned_days, load.assigned_without_estimate)}
        </div>
      )}

      <div className="td-card-status">
        <StatusCounters
          counts={dev.status_counts ?? {}}
          statuses={statuses}
          statusGroups={statusGroups}
          selected={selected ? statusFilter : null}
          onSelect={onStatusFilter}
        />
      </div>

      <div className={`td-card-flags${flags.length ? ' has-flags' : ''}`}>
        {flags.length === 0 && <span>Без замечаний</span>}
        {flags.map((flag, i) => {
          const active = selected && flagFilter === flag;
          return (
            <span key={flag}>
              {i > 0 && ' · '}
              <button
                type="button"
                className={`td-flag-link${active ? ' is-active' : ''}${flag === 'over' ? ' is-red' : ''}`}
                title={`${FLAG_LABELS[flag]} — показать только эти`}
                aria-pressed={active}
                onClick={(e) => {
                  e.stopPropagation();
                  onFlagFilter(active ? null : flag);
                }}
              >
                {FLAG_LABELS[flag]} <span className="num">{dev.flag_counts[flag]}</span>
              </button>
            </span>
          );
        })}
      </div>
    </article>
  );
}
