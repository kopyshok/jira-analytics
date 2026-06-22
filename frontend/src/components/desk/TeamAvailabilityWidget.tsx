import { Tooltip } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { initials, fmtShortRange } from './format';
import { deskStatusKind } from './deskStatus';
import { MONTH_NAMES } from '../../utils/constants';
import type { AvailabilityMember, DeskProject, TeamAvailabilityData } from '../../types/desk';

const AV_CLASSES = ['desk-av-1', 'desk-av-2', 'desk-av-3', 'desk-av-4'];

function toTime(iso: string): number {
  return new Date(iso.slice(0, 10)).getTime();
}

/** Метки месяцев внутри [start, end] — по одной на месяц. */
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

/** Границы месяцев в процентах — вертикальные разделители трека. */
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

const LANE_H = 22; // высота одной дорожки полос, px

type LanedProject = { p: DeskProject; lane: number };

/** Разложить полосы по дорожкам так, чтобы пересекающиеся не накладывались. */
function packLanes(projects: DeskProject[]): { laned: LanedProject[]; lanes: number } {
  const dated = projects
    .filter((p) => p.start_date && p.end_date)
    .sort((a, b) => toTime(a.start_date!) - toTime(b.start_date!));
  const laneEnds: number[] = [];
  const laned: LanedProject[] = [];
  for (const p of dated) {
    const s = toTime(p.start_date!);
    const e = toTime(p.end_date!);
    let lane = laneEnds.findIndex((end) => end <= s);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(e);
    } else {
      laneEnds[lane] = e;
    }
    laned.push({ p, lane });
  }
  return { laned, lanes: Math.max(1, laneEnds.length) };
}

function ProjectBar({ p, lane, qStart, qEnd }: { p: DeskProject; lane: number; qStart: string; qEnd: string }) {
  const qs = toTime(qStart);
  const qe = toTime(qEnd);
  const span = qe - qs || 1;
  const bStart = Math.max(toTime(p.start_date!), qs);
  const bEnd = Math.min(toTime(p.end_date!), qe);
  const left = ((bStart - qs) / span) * 100;
  const width = Math.max(1.5, ((bEnd - bStart) / span) * 100);
  const kind = deskStatusKind(p.status);
  const label = p.title ?? p.key ?? '—';
  const tip = (
    <span>
      {p.key ? `${p.key} · ` : ''}{label}
      <br />
      {fmtShortRange(p.start_date, p.end_date)}
      {p.status ? ` · ${p.status}` : ''}
    </span>
  );
  return (
    <Tooltip title={tip} mouseEnterDelay={0.2}>
      <div
        className={`desk-tl-bar desk-bar-${kind}`}
        style={{ left: `${left}%`, width: `${width}%`, top: `${lane * LANE_H + 3}px` }}
      >
        {p.key ?? label}
      </div>
    </Tooltip>
  );
}

function MemberRow({ m, avIdx, qStart, qEnd, gridlines, nowLeft }: {
  m: AvailabilityMember;
  avIdx: number;
  qStart: string;
  qEnd: string;
  gridlines: number[];
  nowLeft: number | null;
}) {
  const { laned, lanes } = packLanes(m.projects);
  return (
    <div className="desk-av-row">
      <div className="desk-av-who">
        <div className={`desk-member-avatar ${AV_CLASSES[avIdx % AV_CLASSES.length]}`}>
          {initials(m.display_name)}
        </div>
        <div className="desk-av-who-text">
          <div className="desk-member-name">{m.display_name}</div>
          <div className="desk-member-count">проектов: {m.projects.length}</div>
        </div>
      </div>
      <div className="desk-av-track" style={{ height: `${lanes * LANE_H + 6}px` }}>
        {gridlines.map((g, i) => (
          <div key={i} className="desk-tl-gridline" style={{ left: `${g}%` }} />
        ))}
        {laned.map(({ p, lane }, i) => (
          <ProjectBar key={`${p.key ?? ''}-${i}`} p={p} lane={lane} qStart={qStart} qEnd={qEnd} />
        ))}
        {nowLeft !== null && <div className="desk-tl-now" style={{ left: `${nowLeft}%` }} />}
      </div>
    </div>
  );
}

export default function TeamAvailabilityWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<TeamAvailabilityData>(token, 'team_availability');
  const members = (data?.members ?? []).filter((m) => m.projects.length > 0);
  const qStart = data?.quarter_start ?? '';
  const qEnd = data?.quarter_end ?? '';

  const labels = qStart && qEnd ? monthLabels(qStart, qEnd) : [];
  const gridlines = qStart && qEnd ? monthGridlines(qStart, qEnd) : [];

  let nowLeft: number | null = null;
  if (qStart && qEnd) {
    const qs = toTime(qStart);
    const qe = toTime(qEnd);
    const now = new Date().getTime();
    if (now >= qs && now <= qe) nowLeft = ((now - qs) / (qe - qs || 1)) * 100;
  }

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={members.length === 0}
      emptyText="Нет занятости команды"
    >
      <div className="desk-av-header">
        <div />
        <div className="desk-av-months" style={{ gridTemplateColumns: `repeat(${labels.length || 1}, 1fr)` }}>
          {labels.map((mo, i) => (
            <div key={i} className="desk-tl-month-label">{mo}</div>
          ))}
        </div>
      </div>
      <div className="desk-av-list">
        {members.map((m, i) => (
          <MemberRow
            key={m.id}
            m={m}
            avIdx={i}
            qStart={qStart}
            qEnd={qEnd}
            gridlines={gridlines}
            nowLeft={nowLeft}
          />
        ))}
      </div>
    </WidgetShell>
  );
}
