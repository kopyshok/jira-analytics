import { Tooltip } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtShortRange } from './format';
import { deskStatusKind } from './deskStatus';
import { MONTH_NAMES } from '../../utils/constants';
import type { MyTimelineData, TimelineBar } from '../../types/desk';

function toTime(iso: string): number {
  return new Date(iso.slice(0, 10)).getTime();
}

/** Метки месяцев внутри [start, end] — равные доли по числу месяцев. */
function monthLabels(startIso: string, endIso: string): string[] {
  const start = new Date(startIso.slice(0, 10));
  const end = new Date(endIso.slice(0, 10));
  const out: string[] = [];
  const cur = new Date(start.getFullYear(), start.getMonth(), 1);
  while (cur.getTime() <= end.getTime()) {
    out.push((MONTH_NAMES[cur.getMonth() + 1] ?? '').slice(0, 3));
    cur.setMonth(cur.getMonth() + 1);
  }
  return out;
}

/** Позиции границ месяцев в процентах (для вертикальных разделителей). */
function monthGridlines(startIso: string, endIso: string): number[] {
  const start = toTime(startIso);
  const end = toTime(endIso);
  const span = end - start || 1;
  const out: number[] = [];
  const cur = new Date(startIso.slice(0, 10));
  cur.setMonth(cur.getMonth() + 1, 1);
  while (cur.getTime() < end) {
    out.push(((cur.getTime() - start) / span) * 100);
    cur.setMonth(cur.getMonth() + 1);
  }
  return out;
}

type TimelineBarView = TimelineBar & { jira_url_safe: string | null };

const LANE_H = 22; // высота дорожки полос внутри строки проекта, px

/** Разложить фазы по дорожкам, чтобы пересекающиеся полосы не накладывались. */
function packLanes(segments: TimelineBarView[]): { laned: { seg: TimelineBarView; lane: number }[]; lanes: number } {
  const sorted = [...segments].sort((a, b) => toTime(a.start_date) - toTime(b.start_date));
  const laneEnds: number[] = [];
  const laned = sorted.map((seg) => {
    const s = toTime(seg.start_date);
    const e = toTime(seg.end_date);
    let lane = laneEnds.findIndex((end) => end <= s);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(e);
    } else {
      laneEnds[lane] = e;
    }
    return { seg, lane };
  });
  return { laned, lanes: Math.max(1, laneEnds.length) };
}

/** Одна строка — одна задача; несколько отрезков назначения как полосы. */
function GroupRow({ segments, gridlines, nowLeft, qStart, qEnd }: {
  segments: TimelineBarView[]; gridlines: number[]; nowLeft: number | null; qStart: string; qEnd: string;
}) {
  const qs = toTime(qStart);
  const qe = toTime(qEnd);
  const span = qe - qs || 1;
  const head = segments[0];
  const label = head.title ?? head.key ?? '—';
  const jiraUrl = head.jira_url_safe;
  const { laned, lanes } = packLanes(segments);

  // Факт-полоса по задаче (одинакова на всех отрезках) — рисуем один раз.
  let fact: { left: number; width: number } | null = null;
  if (head.fact_start && head.fact_end) {
    const fs = Math.max(toTime(head.fact_start), qs);
    const fe = Math.min(toTime(head.fact_end), qe);
    if (fe >= fs) {
      fact = { left: ((fs - qs) / span) * 100, width: Math.max(1, ((fe - fs) / span) * 100) };
    }
  }

  const planRange = segments.length > 1
    ? segments.map((s) => fmtShortRange(s.start_date, s.end_date)).join(', ')
    : fmtShortRange(head.start_date, head.end_date);
  const tip = (
    <span>
      {head.key ? `${head.key} · ` : ''}{label}
      <br />
      План: {planRange}
      {head.fact_start && head.fact_end && (
        <><br />Факт: {fmtShortRange(head.fact_start, head.fact_end)}</>
      )}
      {head.status ? <><br />{head.status}</> : null}
    </span>
  );

  return (
    <div className="desk-tl-row">
      <div className="desk-tl-label" title={`${head.key ? `${head.key} · ` : ''}${label}`}>
        {head.key && (
          jiraUrl
            ? <a className="desk-jira-key desk-jira-key-link" href={jiraUrl} target="_blank" rel="noreferrer">{head.key}</a>
            : <span className="desk-jira-key">{head.key}</span>
        )}
        <span className="desk-tl-label-text">
          {jiraUrl ? <a href={jiraUrl} target="_blank" rel="noreferrer">{label}</a> : label}
        </span>
      </div>
      <div className="desk-tl-track" style={{ height: `${lanes * LANE_H + 6}px` }}>
        {gridlines.map((g, i) => (
          <div key={i} className="desk-tl-gridline" style={{ left: `${g}%` }} />
        ))}
        {laned.map(({ seg, lane }, i) => {
          const bStart = Math.max(toTime(seg.start_date), qs);
          const bEnd = Math.min(toTime(seg.end_date), qe);
          const left = ((bStart - qs) / span) * 100;
          const width = Math.max(2, ((bEnd - bStart) / span) * 100);
          const kind = deskStatusKind(seg.status);
          const segTip = (
            <span>
              {seg.key ? `${seg.key} · ` : ''}{seg.phase_label}
              <br />
              План: {fmtShortRange(seg.start_date, seg.end_date)}
              {seg.status ? <><br />{seg.status}</> : null}
            </span>
          );
          return (
            <Tooltip key={i} title={segTip} mouseEnterDelay={0.2}>
              <div
                className={`desk-tl-bar desk-bar-${kind}`}
                style={{ left: `${left}%`, width: `${width}%`, top: `${lane * LANE_H + 3}px` }}
              >
                {seg.phase_label}
              </div>
            </Tooltip>
          );
        })}
        {fact && (
          <Tooltip title={tip} mouseEnterDelay={0.2}>
            <div className="desk-tl-fact" style={{ left: `${fact.left}%`, width: `${fact.width}%` }} />
          </Tooltip>
        )}
        {nowLeft !== null && <div className="desk-tl-now" style={{ left: `${nowLeft}%` }} />}
      </div>
    </div>
  );
}

/** Группировка полос по задаче (key), сохраняя порядок первого появления. */
function groupByKey(bars: TimelineBarView[]): TimelineBarView[][] {
  const groups: TimelineBarView[][] = [];
  const idx = new Map<string, number>();
  bars.forEach((b) => {
    const k = b.key ?? `__${groups.length}`;
    if (idx.has(k)) {
      groups[idx.get(k)!].push(b);
    } else {
      idx.set(k, groups.length);
      groups.push([b]);
    }
  });
  return groups;
}

export default function MyTimelineWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<MyTimelineData>(token, 'my_timeline');
  const bars = (data?.bars ?? []).map((b) => ({
    ...b,
    jira_url_safe: b.key ? `https://example.atlassian.net/browse/${b.key}` : null,
  }));
  const qStart = data?.quarter_start ?? '';
  const qEnd = data?.quarter_end ?? '';

  const labels = qStart && qEnd ? monthLabels(qStart, qEnd) : [];
  const gridlines = qStart && qEnd ? monthGridlines(qStart, qEnd) : [];

  // Текущая неделя: позиция «сегодня» в процентах квартала (если внутри).
  let nowLeft: number | null = null;
  if (qStart && qEnd) {
    const qs = toTime(qStart);
    const qe = toTime(qEnd);
    const now = new Date().getTime();
    if (now >= qs && now <= qe) nowLeft = ((now - qs) / (qe - qs || 1)) * 100;
  }

  const todayLabel = new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={bars.length === 0}
      emptyText="Нет проектов с датами"
    >
      <div>
        <div className="desk-tl-header">
          <div />
          <div className="desk-tl-months" style={{ gridTemplateColumns: `repeat(${labels.length || 1}, 1fr)` }}>
            {labels.map((m, i) => (
              <div key={i} className="desk-tl-month-label">{m}</div>
            ))}
          </div>
        </div>
        <div className="desk-tl-rows">
          {groupByKey(bars).map((segments, i) => (
            <GroupRow
              key={`${segments[0].key ?? ''}-${i}`}
              segments={segments}
              gridlines={gridlines}
              nowLeft={nowLeft}
              qStart={qStart}
              qEnd={qEnd}
            />
          ))}
        </div>

        {nowLeft !== null && (
          <div className="desk-tl-legend">
            <span className="desk-tl-legend-dot" />
            Текущая неделя ({todayLabel})
          </div>
        )}
        <div className="desk-tl-color-legend">
          <span className="desk-tl-color-item"><span className="desk-tl-fact-swatch" />Факт (по списаниям)</span>
          <span className="desk-tl-color-item"><span className="desk-tl-color-swatch desk-bar-active" />В работе</span>
          <span className="desk-tl-color-item"><span className="desk-tl-color-swatch desk-bar-review" />На ревью</span>
          <span className="desk-tl-color-item"><span className="desk-tl-color-swatch desk-bar-done" />Готово</span>
          <span className="desk-tl-color-item"><span className="desk-tl-color-swatch desk-bar-returned" />Возвращена</span>
        </div>
      </div>
    </WidgetShell>
  );
}
