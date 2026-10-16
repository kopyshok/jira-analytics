import { Tooltip } from 'antd';
import {
  FLAG_LABELS, FLAG_ORDER, roundHours,
  type DeskDeveloper, type DeskWorkload, type FlagCode,
} from '../../../../api/teamDesk';
import type { QueueScope } from '../../../../components/teamdesk/queueFilter';
import { StatusCounters } from '../../../../components/teamdesk/StatusCounters';

function initials(name: string | null): string {
  if (!name) return '?';
  const parts = name.split(' ');
  return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase();
}

/** Точность оценок: перерасход — красным, недорасход — янтарём. */
function accuracyTone(value: number | null): string | undefined {
  if (value == null) return undefined;
  if (value > 1.3) return 'is-bad';
  if (value < 0.7) return 'is-warn';
  return undefined;
}

/** Главное замечание на плитке — метка справа от имени. */
function headlineFlag(dev: DeskDeveloper): FlagCode | null {
  if (dev.flag_counts.over) return 'over';
  if (dev.flag_counts.decomp) return 'decomp';
  if (dev.flag_counts.stale) return 'stale';
  return null;
}

interface Props {
  developers: DeskDeveloper[];
  workload: Record<string, DeskWorkload>;
  overrunPct: number;
  selected: string | null;
  onSelect: (id: string | null) => void;
  statuses: string[];
  statusGroups?: Record<string, string[]>;
  statusFilter: string | null;
  onStatusFilter: (developerId: string, status: string | null) => void;
  queueScope: QueueScope;
  onQueueFilter: (developerId: string, scope: QueueScope) => void;
  flagFilter: FlagCode | null;
  onFlagFilter: (developerId: string, flag: FlagCode | null) => void;
}

/**
 * «Светофор» в скине «Цветовые зоны»: плитки разработчиков одной лентой,
 * лишние листаются вбок. Те же отборы, что у плиток Aurora: щелчок по плитке,
 * по строке очереди, по статусу и по замечанию.
 */
export function DeskDevCards({
  developers, workload, overrunPct, selected, onSelect,
  statuses, statusGroups, statusFilter, onStatusFilter,
  queueScope, onQueueFilter, flagFilter, onFlagFilter,
}: Props) {
  return (
    <section className="dz-cards" aria-label="Светофор">
      {developers.map((dev) => {
        const load = workload[dev.developer_id];
        const isSelected = selected === dev.developer_id;
        const head = headlineFlag(dev);
        const est = dev.est_hours || null;
        const ratio = est ? dev.fact_hours / est : 0;
        const over = !!est && ratio > 1 + overrunPct / 100;
        const flags = FLAG_ORDER.filter((f) => dev.flag_counts[f]);
        const queue = (scope: Exclude<QueueScope, null>) => {
          onQueueFilter(dev.developer_id, isSelected && queueScope === scope ? null : scope);
        };
        return (
          <article
            key={dev.developer_id}
            className={`zn-card dz-card${isSelected ? ' is-selected' : ''}`}
            role="button"
            tabIndex={0}
            aria-pressed={isSelected}
            onClick={() => onSelect(isSelected ? null : dev.developer_id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(isSelected ? null : dev.developer_id);
              }
            }}
          >
            <div className="dz-card-top">
              <div className="dz-card-total">
                <b>{dev.total_issues}</b>
                <span>задач всего</span>
              </div>
              <div className="dz-card-main">
                <div className="dz-card-name">
                  <span className="dz-avatar">{initials(dev.display_name)}</span>
                  <span className="dz-card-who">
                    <b>{dev.display_name ?? 'Без имени'}</b>
                    {dev.team && <span> {dev.team}</span>}
                  </span>
                  {head && (
                    <span className={`dz-card-flag${head === 'over' ? ' is-bad' : ''}`}>{FLAG_LABELS[head]}</span>
                  )}
                </div>
                <div className="dz-card-split">
                  <b className="is-dev">{dev.in_dev}</b> у него · <b className="is-wait">{dev.waiting}</b> ждут не его · <b className="is-todo">{dev.todo}</b> не начаты
                </div>
                <Tooltip title={est ? `Факт ${roundHours(dev.fact_hours)} ч из ${roundHours(est)} ч` : 'Оценки нет'}>
                  <div className="dz-card-hours">
                    <span>{roundHours(dev.fact_hours)} / {est == null ? '—' : roundHours(est)} ч</span>
                    <div className="dz-card-bar">
                      {est != null && (
                        <>
                          <i style={{ width: `${Math.min(ratio, 1) * 62.5}%` }} />
                          {ratio > 1 && (
                            <i className="is-over" style={{ left: '62.5%', width: `${Math.min(ratio - 1, 0.6) * 62.5}%` }} />
                          )}
                          <u />
                        </>
                      )}
                    </div>
                    <span className="dz-card-acc">
                      точность <b className={accuracyTone(dev.accuracy) ?? (over ? 'is-bad' : undefined)}>
                        {dev.accuracy == null ? '—' : `×${dev.accuracy.toFixed(2)}`}
                      </b>
                    </span>
                  </div>
                </Tooltip>
              </div>
            </div>
            {load && (
              <>
                <button
                  type="button"
                  className={`dz-queue${isSelected && queueScope === 'all' ? ' is-active' : ''}`}
                  onClick={(e) => { e.stopPropagation(); queue('all'); }}
                >
                  <span>Очередь</span>
                  <span>
                    {roundHours(load.queue_hours)} ч{load.queue_days != null ? ` ≈ ${load.queue_days} дн` : ' · нет свободных дней'}
                    {load.without_estimate > 0 ? ` · ещё ${load.without_estimate} без оценки` : ''}
                  </span>
                </button>
                <button
                  type="button"
                  className={`dz-queue${isSelected && queueScope === 'assigned' ? ' is-active' : ''}`}
                  onClick={(e) => { e.stopPropagation(); queue('assigned'); }}
                >
                  <span>Очередь к выполнению</span>
                  <span>
                    {roundHours(load.assigned_hours)} ч{load.assigned_days != null ? ` ≈ ${load.assigned_days} дн` : ' · нет свободных дней'}
                    {load.assigned_without_estimate > 0 ? ` · ещё ${load.assigned_without_estimate} без оценки` : ''}
                  </span>
                </button>
              </>
            )}
            <div className="dz-card-statuses">
              <StatusCounters
                counts={dev.status_counts ?? {}}
                statuses={statuses}
                statusGroups={statusGroups}
                selected={isSelected ? statusFilter : null}
                onSelect={(status) => onStatusFilter(dev.developer_id, status)}
              />
            </div>
            <div className="dz-card-notes">
              {flags.length === 0 ? (
                <span className="dz-card-clean">без замечаний</span>
              ) : (
                <>
                  Замечания:{' '}
                  {flags.map((flag, i) => {
                    const active = isSelected && flagFilter === flag;
                    return (
                      <span key={flag}>
                        {i > 0 && ' · '}
                        <button
                          type="button"
                          className={`dz-note${flag === 'over' ? ' is-bad' : ' is-warn'}${active ? ' is-active' : ''}`}
                          title={`${FLAG_LABELS[flag]} — показать только эти`}
                          onClick={(e) => {
                            e.stopPropagation();
                            onFlagFilter(dev.developer_id, active ? null : flag);
                          }}
                        >
                          {FLAG_LABELS[flag]} {dev.flag_counts[flag]}
                        </button>
                      </span>
                    );
                  })}
                </>
              )}
            </div>
          </article>
        );
      })}
    </section>
  );
}
