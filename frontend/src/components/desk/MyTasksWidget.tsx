import { useState } from 'react';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtShortRange } from './format';
import { deskStatusKind, isInProgress, STATUS_BADGE_LABEL } from './deskStatus';
import type { DeskProject, MyTasksData, ProjectChild } from '../../types/desk';

function pctClass(p: DeskProject): { pct: string; fill: string } {
  const overZeroPlan = p.norm_hours === 0 && p.fact_hours > 0;
  if (overZeroPlan || p.pct > 110) return { pct: 'desk-pct-over', fill: 'desk-fill-over' };
  if (p.pct >= 70) return { pct: 'desk-pct-ok', fill: 'desk-fill-ok' };
  return { pct: 'desk-pct-low', fill: 'desk-fill-low' };
}

function JiraKey({ k, url }: { k: string; url: string | null }) {
  return url ? (
    <a className="desk-jira-key desk-jira-key-link" href={url} target="_blank" rel="noreferrer">{k}</a>
  ) : (
    <span className="desk-jira-key">{k}</span>
  );
}

function ChildRow({ c }: { c: ProjectChild }) {
  const kind = deskStatusKind(c.status);
  return (
    <div className="desk-child-row">
      <span className={`desk-status-dot desk-dot-${kind}`} />
      {c.key && <JiraKey k={c.key} url={c.jira_url} />}
      <span className="desk-child-name">
        {c.jira_url ? (
          <a href={c.jira_url} target="_blank" rel="noreferrer">{c.title ?? c.key ?? '—'}</a>
        ) : (c.title ?? c.key ?? '—')}
      </span>
      <span className="desk-child-hrs">{Math.round(c.fact_hours)} ч</span>
    </div>
  );
}

function ProjectRow({ p, activeNow }: { p: DeskProject; activeNow: boolean }) {
  const [open, setOpen] = useState(false);
  const kind = deskStatusKind(p.status);
  const { pct, fill } = pctClass(p);
  const fillW = p.norm_hours > 0
    ? Math.min(100, (p.fact_hours / p.norm_hours) * 100)
    : (p.fact_hours > 0 ? 100 : 0);
  const badgeLabel = p.status ?? STATUS_BADGE_LABEL[kind];
  const children = p.children ?? [];
  const hasChildren = children.length > 0;

  return (
    <div className={`desk-project-row${activeNow ? ' active-now' : ''}`}>
      <span
        className={`desk-tree-chevron${open ? ' open' : ''}${hasChildren ? '' : ' hidden'}`}
        role={hasChildren ? 'button' : undefined}
        onClick={() => hasChildren && setOpen((o) => !o)}
      >▸</span>
      <span className={`desk-status-dot desk-dot-${kind}`} />
      <div className="desk-project-meta">
        <div className="desk-project-name">
          {p.jira_url ? (
            <a href={p.jira_url} target="_blank" rel="noreferrer">{p.title ?? p.key ?? '—'}</a>
          ) : (p.title ?? p.key ?? '—')}
        </div>
        <div className="desk-project-sub">
          {p.key && <JiraKey k={p.key} url={p.jira_url} />}
          <span className="desk-project-dates">{fmtShortRange(p.start_date, p.end_date)}</span>
          {badgeLabel && <span className={`desk-status-badge desk-badge-${kind}`}>{badgeLabel}</span>}
          {hasChildren && (
            <button type="button" className="desk-child-toggle" onClick={() => setOpen((o) => !o)}>
              {open ? 'скрыть' : 'подзадачи'} ({children.length})
            </button>
          )}
          {activeNow && <span className="desk-now-pill">сейчас</span>}
        </div>
        {open && hasChildren && (
          <div className="desk-child-list">
            {children.map((c, i) => (
              <ChildRow key={`${c.key ?? ''}-${i}`} c={c} />
            ))}
          </div>
        )}
      </div>
      <div className="desk-project-right">
        <div className="desk-hours-label">
          {Math.round(p.fact_hours)} / {Math.round(p.norm_hours)} ч
          <span className={`pct ${pct}`}>{Math.round(p.pct)}%</span>
        </div>
        <div className="desk-progress-bar">
          <div className={`desk-progress-fill ${fill}`} style={{ width: `${fillW}%` }} />
        </div>
      </div>
    </div>
  );
}

export default function MyTasksWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<MyTasksData>(token, 'my_tasks');
  const projects = data?.projects ?? [];

  // Подсветка «в работе сейчас» — первый проект с активным статусом.
  const activeIdx = projects.findIndex((p) => isInProgress(p.status));

  const totalNorm = projects.reduce((s, p) => s + p.norm_hours, 0);
  const totalFact = projects.reduce((s, p) => s + p.fact_hours, 0);
  const totalPct = totalNorm > 0 ? Math.round((totalFact / totalNorm) * 100) : 0;

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={projects.length === 0}
      emptyText="Нет проектов"
    >
      <div className="desk-tasks-summary">
        <div className="desk-tasks-summary-item">
          <span className="desk-tasks-summary-val">{projects.length}</span>
          <span className="desk-tasks-summary-unit">проектов</span>
        </div>
        <div className="desk-tasks-summary-item">
          <span className="desk-tasks-summary-val">
            {Math.round(totalFact)} / {Math.round(totalNorm)} ч
          </span>
          <span className="desk-tasks-summary-unit">факт / план</span>
        </div>
        <div className="desk-tasks-summary-item">
          <span className="desk-tasks-summary-val">{totalPct}%</span>
          <span className="desk-tasks-summary-unit">загрузка</span>
        </div>
      </div>
      <div className="desk-project-list">
        {projects.map((p, i) => (
          <ProjectRow
            key={`${p.key ?? ''}-${p.start_date ?? ''}-${i}`}
            p={p}
            activeNow={i === activeIdx}
          />
        ))}
      </div>
    </WidgetShell>
  );
}
