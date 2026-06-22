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

function BarRow({ bar, gridlines, nowLeft, qStart, qEnd }: {
  bar: TimelineBarView; gridlines: number[]; nowLeft: number | null; qStart: string; qEnd: string;
}) {
  const qs = toTime(qStart);
  const qe = toTime(qEnd);
  const span = qe - qs || 1;
  const bStart = Math.max(toTime(bar.start_date), qs);
  const bEnd = Math.min(toTime(bar.end_date), qe);
  const left = ((bStart - qs) / span) * 100;
  const width = Math.max(2, ((bEnd - bStart) / span) * 100);
  const kind = deskStatusKind(bar.status);
  const label = bar.title ?? bar.key ?? '—';
  const jiraUrl = bar.jira_url_safe;

  // Факт-полоса: диапазон дат ворклогов внутри квартала (если есть).
  let fact: { left: number; width: number } | null = null;
  if (bar.fact_start && bar.fact_end) {
    const fs = Math.max(toTime(bar.fact_start), qs);
    const fe = Math.min(toTime(bar.fact_end), qe);
    if (fe >= fs) {
      fact = { left: ((fs - qs) / span) * 100, width: Math.max(1, ((fe - fs) / span) * 100) };
    }
  }

  const tip = (
    <span>
      {bar.key ? `${bar.key} · ` : ''}{label}
      <br />
      План: {fmtShortRange(bar.start_date, bar.end_date)}
      {bar.fact_start && bar.fact_end && (
        <>
          <br />
          Факт: {fmtShortRange(bar.fact_start, bar.fact_end)}
        </>
      )}
      {bar.status ? <><br />{bar.status}</> : null}
    </span>
  );

  return (
    <div className="desk-tl-row">
      <div className="desk-tl-label" title={`${bar.key ? `${bar.key} · ` : ''}${label}`}>
        {bar.key && (
          jiraUrl
            ? <a className="desk-jira-key desk-jira-key-link" href={jiraUrl} target="_blank" rel="noreferrer">{bar.key}</a>
            : <span className="desk-jira-key">{bar.key}</span>
        )}
        <span className="desk-tl-label-text">
          {jiraUrl ? <a href={jiraUrl} target="_blank" rel="noreferrer">{label}</a> : label}
        </span>
      </div>
      <div className="desk-tl-track">
        {gridlines.map((g, i) => (
          <div key={i} className="desk-tl-gridline" style={{ left: `${g}%` }} />
        ))}
        <Tooltip title={tip} mouseEnterDelay={0.2}>
          <div className={`desk-tl-bar desk-bar-${kind}`} style={{ left: `${left}%`, width: `${width}%` }}>
            {label}
          </div>
        </Tooltip>
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

export default function MyTimelineWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<MyTimelineData>(token, 'my_timeline');
  const bars = (data?.bars ?? []).map((b) => ({
    ...b,
    jira_url_safe: b.key ? `https://itgri.atlassian.net/browse/${b.key}` : null,
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
          {bars.map((bar, i) => (
            <BarRow
              key={`${bar.key ?? ''}-${bar.start_date}-${i}`}
              bar={bar}
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
