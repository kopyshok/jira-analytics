import { useState } from 'react';
import { AlertTriangle, Info } from 'lucide-react';
import type { Portfolio } from '../../../../types/projects';
import { PhaseTimeline } from '../../../../components/projects/plan/PhaseTimeline';
import { PortfolioProjectsTable } from '../../../../components/projects/plan/PortfolioProjectsTable';
import ZonesBand from '../../ZonesBand';

const fmt = (n: number) => Math.round(n).toLocaleString('ru-RU');

/** Подпись сортировки таблицы проектов — по колонке, которую выбрал пользователь. */
const SORT_BY: Record<string, string> = {
  title: 'по названию',
  hours: 'по факту часов',
  pct: 'по загрузке',
  analyst: 'по анализу',
  dev: 'по разработке',
  qa: 'по тестированию',
  external: 'по внешним часам',
};
function sortCaption(sort: { key: string; order: 'ascend' | 'descend' } | null): string {
  if (!sort) return 'без сортировки';
  const by = SORT_BY[sort.key] ?? 'по выбранной колонке';
  return `сортировка ${by}, ${sort.order === 'descend' ? 'по убыванию' : 'по возрастанию'}`;
}

interface Props {
  data: Portfolio;
  countLabel: string;
  onOpen: (key: string) => void;
}

/**
 * Сводка портфеля в скине «Цветовые зоны»: итоги, фазы и сигналы — в полосе
 * зоны крупными числами; в теле таблица проектов и таймлайн, каждый листается
 * внутри своего блока.
 */
export function PortfolioZones({ data, countLabel, onOpen }: Props) {
  const pct = data.total_pct;
  // Таблица открывается отсортированной по загрузке (по убыванию) — дальше как выберет пользователь.
  const [sort, setSort] = useState<{ key: string; order: 'ascend' | 'descend' } | null>({ key: 'pct', order: 'descend' });
  const pctState = pct == null ? '' : pct > 110 ? ' · перегруз' : pct >= 70 ? ' · в норме (от 70%)' : ' · ниже нормы (от 70%)';
  return (
    <>
      <ZonesBand eyebrow="Обзор / Проекты" title="Сводка портфеля">
        <div className="zn-band-row pz-stats" data-testid="portfolio-summary">
          <span className="pz-stat">
            <b className="pz-stat-big">{data.project_count}</b>
            <span>{countLabel}</span>
          </span>
          <span className="pz-stat">
            <b className="pz-stat-big">{fmt(data.total_fact)}</b>
            <b className="pz-stat-mid">/ {data.total_plan == null ? '—' : `${fmt(data.total_plan)} ч`}</b>
            <span>{data.total_plan == null ? 'план не заведён' : 'всего факт / план'}</span>
          </span>
          <span className="pz-stat">
            <b className={`pz-stat-big pz-stat-pct${pct != null && pct > 110 ? ' is-over' : ''}`}>{pct == null ? '—' : `${pct}%`}</b>
            <span>загрузка{pctState}</span>
          </span>
          <span className="pz-stat-phases">
            {data.work_types.map((wt) => (
              <span key={wt.code} className="pz-phase" data-phase={wt.code}>
                <i aria-hidden />
                {wt.label} <b>{fmt(wt.fact_hours)} / {fmt(wt.plan_hours)} ч</b>
                {wt.pct != null && <> · {wt.pct}%</>}
              </span>
            ))}
            {data.external_hours > 0 && (
              <span className="pz-phase" data-phase="external" title="Часы сотрудников не из команды — вне плана и факта">
                <i aria-hidden />Внешние <b>{fmt(data.external_hours)} ч</b>
              </span>
            )}
          </span>
        </div>
        {data.signals.length > 0 && (
          <div className="zn-band-row" data-testid="portfolio-signals">
            {data.signals.map((s) => (
              <span key={s.kind} className={`pz-signal is-${s.severity}`}>
                {s.severity === 'warn'
                  ? <AlertTriangle size={14} strokeWidth={1.6} aria-hidden />
                  : <Info size={14} strokeWidth={1.6} aria-hidden />}
                {s.text}
              </span>
            ))}
          </div>
        )}
      </ZonesBand>

      <section className="zn-card pz-table" aria-label="Проекты портфеля">
        <div className="zn-card-head pz-card-head">
          <h2>Проекты портфеля</h2>
          <span className="zn-card-sub">{sortCaption(sort)}</span>
        </div>
        <PortfolioProjectsTable
          projects={data.projects}
          timeline={data.timeline}
          totals={{
            workTypes: data.work_types,
            externalHours: data.external_hours,
            totalPlan: data.total_plan,
            totalFact: data.total_fact,
            totalPct: data.total_pct,
          }}
          onRowClick={onOpen}
          maxHeight="var(--pz-table-h)"
          titleWidth={340}
          onSortChange={(key, order) => setSort(key && order ? { key, order } : null)}
        />
      </section>

      <section className="zn-card pz-timeline" aria-label="Таймлайн портфеля">
        <div className="zn-card-head pz-card-head">
          <h2>Таймлайн портфеля</h2>
        </div>
        <div className="pz-timeline-body">
          <PhaseTimeline
            timeline={data.timeline}
            mode="by-project"
            maxHeight="var(--pz-timeline-h)"
            onRowClick={onOpen}
            todayPill
          />
        </div>
      </section>
    </>
  );
}
