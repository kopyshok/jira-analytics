import { useLayoutEffect, useRef, useState } from 'react';
import { Tooltip } from 'antd';
import { CheckOutlined, RightOutlined } from '@ant-design/icons';
import {
  FLAG_LABELS, FLAG_ORDER, roundHours,
  type DeskDeveloper, type DeskWorkload, type FlagCode,
} from '../../../api/teamDesk';
import type { QueueScope } from '../../../components/teamdesk/queueFilter';
import { StatusCounters } from '../../../components/teamdesk/StatusCounters';
import {
  FLAG_TONE, accuracyLevel, deskAvatarTone, deskInitials, severityBadge,
} from '../../../utils/teamDeskView';

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
 * Подвал плитки — счётчики статусов и замечания. У живых людей пилюль бывает
 * вдвое больше, чем в макете, и самая «длинная» плитка растягивала весь ряд.
 * Подвал держится в две строки; не влезло — кнопка «ещё» раскрывает его целиком.
 */
function CardFoot({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [overflow, setOverflow] = useState(false);
  // Переполнение меряется после каждой отрисовки (меняются пилюли) и при
  // изменении ширины плитки.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const check = () => setOverflow(!open && el.scrollHeight > el.clientHeight + 1);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  });
  return (
    <div className="tdc-card-foot-wrap">
      <div ref={ref} className={`tdc-card-foot${open ? '' : ' is-clamped'}`}>{children}</div>
      {(overflow || open) && (
        <button
          type="button"
          className="tdc-card-more"
          aria-expanded={open}
          onClick={(e) => {
            e.stopPropagation();
            setOpen((v) => !v);
          }}
        >
          {open ? 'свернуть' : 'ещё…'}
        </button>
      )}
    </div>
  );
}

/** Строка очереди — кнопка: клик раскладывает её по задачам в таблице ниже. */
function QueueButton({
  label, hours, days, withoutEstimate, active, onClick,
}: {
  label: string;
  hours: number;
  days: number | null;
  withoutEstimate: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={`tdc-queue${active ? ' is-active' : ''}`}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <span>
        <span className="tdc-queue-label">
          {label}{withoutEstimate > 0 ? ` · ещё ${withoutEstimate} без оценки` : ''}
        </span>
        <span className="tdc-queue-value">
          {hours} ч{days != null ? ` ≈ ${days} дн` : ' · нет свободных дней'}
        </span>
      </span>
      <RightOutlined aria-hidden />
    </button>
  );
}

/**
 * Раскладка «Светофор» в скине «Тёплая» (макет C-desk): плитка на
 * разработчика в ряд. Слева — сколько задач и где они, точность оценок;
 * справа — пометка проблемы, факт против оценки и две строки очереди; внизу —
 * счётчики статусов и замечания. Клики те же, что у плиток Aurora.
 */
export default function DeskDeveloperCards({
  developers, workload, overrunPct, selected, onSelect,
  statuses, statusGroups, statusFilter, onStatusFilter,
  queueScope, onQueueFilter, flagFilter, onFlagFilter,
}: Props) {
  return (
    <section className="tdc-cards" aria-label="Светофор по разработчикам">
      {developers.map((dev) => {
        const load = workload[dev.developer_id];
        const isSelected = selected === dev.developer_id;
        const badge = severityBadge(dev);
        const tone = deskAvatarTone(dev.display_name);
        const level = accuracyLevel(dev.accuracy);
        const est = dev.est_hours || null;
        const ratio = est ? dev.fact_hours / est : 0;
        const over = ratio > 1 + overrunPct / 100;
        // Перебор — хвостом своей доли: полоса до засечки оценки, дальше — сверх неё.
        const fill = ratio > 1 ? (1 / ratio) * 100 : ratio * 100;
        const flags = FLAG_ORDER.filter((f) => dev.flag_counts[f]);
        return (
          <article
            key={dev.developer_id}
            className={`wr-card tdc-card${isSelected ? ' is-selected' : ''}`}
            role="button"
            tabIndex={0}
            aria-pressed={isSelected}
            aria-label={`${dev.display_name ?? 'Без имени'}: показать только его задачи`}
            onClick={() => onSelect(isSelected ? null : dev.developer_id)}
            onKeyDown={(e) => {
              if (e.target !== e.currentTarget) return;
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(isSelected ? null : dev.developer_id);
              }
            }}
          >
            {/* Имя во всю ширину плитки, пометка проблемы — справа от него. */}
            <div className="tdc-card-top">
              <div className="tdc-card-who">
                <span className="tdc-avatar is-lg" style={{ background: tone.bg, color: tone.fg }}>
                  {deskInitials(dev.display_name)}
                </span>
                <div className="tdc-card-who-text">
                  <div className="tdc-card-name">{dev.display_name ?? 'Без имени'}</div>
                  {dev.team && <div className="tdc-card-team" title={dev.team}>{dev.team}</div>}
                </div>
              </div>
              {badge && <span className={`tdc-badge is-${badge.tone}`}>{badge.label}</span>}
            </div>
            <div className="tdc-card-grid">
              <div className="tdc-card-col">
                <div className="tdc-card-total">
                  <span className="tdc-card-num">{dev.total_issues}</span>
                  <span>задач всего</span>
                </div>
                <div className="tdc-card-split">
                  <span><i className="tdc-dot is-dev" /><b>{dev.in_dev}</b> у него</span>
                  <span><i className="tdc-dot is-waiting" /><b>{dev.waiting}</b> ждут не его</span>
                  <span><i className="tdc-dot is-todo" /><b>{dev.todo}</b> не начаты</span>
                </div>
                <div className="tdc-card-acc">
                  <span>Точность оценок</span>
                  {level ? (
                    <span className={`wr-pill is-sm is-${level}`}>×{dev.accuracy!.toFixed(2)}</span>
                  ) : (
                    <span className="tdc-dash">—</span>
                  )}
                </div>
              </div>

              <div className="tdc-card-col is-right">
                <Tooltip title={est ? `Факт ${roundHours(dev.fact_hours)} ч из ${roundHours(est)} ч · ${Math.round(ratio * 100)}%` : 'Оценки нет'}>
                  <div>
                  <div className="tdc-card-hours">
                    <span>Факт / оценка, ч</span>
                    <b className={over ? 'is-over' : undefined}>
                      {roundHours(dev.fact_hours)} / {est ? roundHours(est) : '—'}
                    </b>
                  </div>
                  <div className="tdc-card-bar">
                    <span className="tdc-card-bar-fill" style={{ width: `${fill}%` }} />
                    {ratio > 1 && (
                      <span className={`tdc-card-bar-tail${over ? ' is-over' : ''}`} style={{ width: `${100 - fill}%` }} />
                    )}
                  </div>
                  </div>
                </Tooltip>
                {load && (
                  <>
                    <QueueButton
                      label="Очередь"
                      hours={load.queue_hours}
                      days={load.queue_days}
                      withoutEstimate={load.without_estimate}
                      active={isSelected && queueScope === 'all'}
                      onClick={() =>
                        onQueueFilter(dev.developer_id, isSelected && queueScope === 'all' ? null : 'all')}
                    />
                    <QueueButton
                      label="Очередь к выполнению"
                      hours={load.assigned_hours}
                      days={load.assigned_days}
                      withoutEstimate={load.assigned_without_estimate}
                      active={isSelected && queueScope === 'assigned'}
                      onClick={() =>
                        onQueueFilter(dev.developer_id, isSelected && queueScope === 'assigned' ? null : 'assigned')}
                    />
                  </>
                )}
              </div>
            </div>

            <CardFoot>
              <StatusCounters
                compact="pill"
                counts={dev.status_counts ?? {}}
                statuses={statuses}
                statusGroups={statusGroups}
                selected={isSelected ? statusFilter : null}
                onSelect={(status) => onStatusFilter(dev.developer_id, status)}
              />
              {flags.map((flag) => {
                const active = isSelected && flagFilter === flag;
                return (
                  <Tooltip key={flag} title={`${FLAG_LABELS[flag]} — показать только эти`}>
                    <button
                      type="button"
                      aria-pressed={active}
                      className={`wr-pill is-sm is-${FLAG_TONE[flag]} tdc-pill is-click${active ? ' is-active' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onFlagFilter(dev.developer_id, active ? null : flag);
                      }}
                    >
                      {FLAG_LABELS[flag]} {dev.flag_counts[flag]}{active ? ' ✕' : ''}
                    </button>
                  </Tooltip>
                );
              })}
              {!flags.length && (
                <span className="tdc-clean"><CheckOutlined aria-hidden />без замечаний</span>
              )}
            </CardFoot>
          </article>
        );
      })}
    </section>
  );
}
