import type { ReactNode } from 'react';
import { FLAG_LABELS, FLAG_ORDER, type FlagCode } from '../../../../api/teamDesk';
import { StatusCounters } from '../../../../components/teamdesk/StatusCounters';
import { ActiveFilters } from '../../../../components/teamdesk/ActiveFilters';
import type { QueueScope } from '../../../../components/teamdesk/queueFilter';

interface Props {
  flagCounts: Partial<Record<FlagCode, number>>;
  flag: FlagCode | null;
  onFlag: (flag: FlagCode | null) => void;
  statusCounts: Record<string, number>;
  statuses: string[];
  statusGroups?: Record<string, string[]>;
  status: string | null;
  onStatus: (status: string | null) => void;
  developerName?: string | null;
  queueScope: QueueScope;
  onReset: () => void;
  /** Строка счётчиков списков, которые открываются в панели подробностей. */
  panels?: ReactNode;
}

/**
 * «Требует внимания» и «Задачи по статусам» одним блоком над таблицей задач —
 * те же отборы, что полосы Aurora: щелчок оставляет в списке только эти задачи.
 * Ниже — счётчики списков (резиновые, в работе одновременно, отсутствия),
 * которые открываются в панели подробностей.
 */
export function DeskAttention({
  flagCounts, flag, onFlag, statusCounts, statuses, statusGroups, status, onStatus,
  developerName, queueScope, onReset, panels,
}: Props) {
  const flags = FLAG_ORDER.filter((f) => flagCounts[f]);
  const anyStatus = statuses.some((s) => statusCounts[s]);
  return (
    <section className="zn-card dz-attention" aria-label="Отборы и статусы" data-tour="desk-flags">
      <div className="dz-attention-row">
        <span className="dz-attention-label">Требует внимания</span>
        {flags.map((f) => {
          const active = flag === f;
          return (
            <button
              key={f}
              type="button"
              className={`dz-flag-chip${f === 'over' ? ' is-bad' : ' is-warn'}${active ? ' is-active' : ''}`}
              aria-pressed={active}
              onClick={() => onFlag(active ? null : f)}
            >
              {FLAG_LABELS[f]}<b>{flagCounts[f]}</b>{active ? ' ✕' : ''}
            </button>
          );
        })}
        {flags.length === 0 && <span className="dz-attention-empty">Замечаний нет</span>}
      </div>
      <div className="dz-attention-row">
        <span className="dz-attention-label">Задачи по статусам</span>
        <StatusCounters
          counts={statusCounts}
          statuses={statuses}
          statusGroups={statusGroups}
          selected={status}
          onSelect={onStatus}
        />
        {!anyStatus && <span className="dz-attention-empty">Задач нет</span>}
      </div>
      {panels}
      <ActiveFilters
        developerName={developerName}
        flag={flag}
        status={status}
        queueScope={queueScope}
        onReset={onReset}
      />
    </section>
  );
}
