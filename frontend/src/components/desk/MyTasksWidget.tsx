import { useState } from 'react';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtShortRange } from './format';
import { deskStatusKind, isInProgress, STATUS_BADGE_LABEL } from './deskStatus';
import type { DeskProject, DeskWorkType, MyTasksData, ProjectChild } from '../../types/desk';

// Цвет вида работ по коду (analyst→cyan, dev→blue, qa→amber, opo→violet).
const WT_COLOR: Record<string, string> = {
  analyst: 'var(--wt-analysis)',
  dev: 'var(--wt-dev)',
  qa: 'var(--wt-test)',
  opo: 'var(--wt-ope)',
};

// Длина окружности кольца (r=14): 2π·14.
const RING_CIRC = 2 * Math.PI * 14;

// Перегруз: план 0 при наличии факта, либо >110%.
function isOver(plan: number, fact: number, pct: number): boolean {
  return (plan === 0 && fact > 0) || pct > 110;
}

function overallPctClass(plan: number, fact: number, pct: number): string {
  if (isOver(plan, fact, pct)) return 'desk-pct-over';
  if (pct >= 70) return 'desk-pct-ok';
  return 'desk-pct-low';
}

function WorkTypeGauge({ wt }: { wt: DeskWorkType }) {
  const over = isOver(wt.plan_hours, wt.fact_hours, wt.pct);
  const shown = Math.max(0, Math.min(100, wt.pct));
  const offset = RING_CIRC * (1 - shown / 100);
  const color = WT_COLOR[wt.code] ?? 'var(--accent)';
  return (
    <div className="desk-ring-card" style={{ ['--wt-c' as string]: color }}>
      <div className="desk-ring">
        <svg viewBox="0 0 38 38">
          <circle className="desk-ring-track" cx="19" cy="19" r="14" />
          <circle
            className={`desk-ring-prog${over ? ' over' : ''}`}
            cx="19"
            cy="19"
            r="14"
            strokeDasharray={RING_CIRC.toFixed(2)}
            strokeDashoffset={over ? 0 : offset.toFixed(2)}
          />
        </svg>
        <div className="desk-ring-center">
          <span className={`desk-ring-pct${over ? ' over' : ''}`}>{Math.round(wt.pct)}%</span>
        </div>
      </div>
      <div className="desk-ring-text">
        <div className="desk-ring-name">{wt.label}</div>
        <div className={`desk-ring-hours mono${over ? ' over' : ''}`}>
          {Math.round(wt.fact_hours)} / {Math.round(wt.plan_hours)} ч
        </div>
      </div>
    </div>
  );
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
  const pct = overallPctClass(p.norm_hours, p.fact_hours, p.pct);
  const badgeLabel = p.status ?? STATUS_BADGE_LABEL[kind];
  const children = p.children ?? [];
  const hasChildren = children.length > 0;
  const workTypes = p.work_types ?? [];

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
          {p.priority != null && (
            <span className="desk-prio-chip" title="Приоритет из сценария">P{p.priority}</span>
          )}
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
        <div className="desk-project-overall">
          <div className="desk-overall-cap">Проект</div>
          <div className="desk-overall-hours mono">
            {Math.round(p.fact_hours)} / {Math.round(p.norm_hours)} ч
          </div>
          <span className={`desk-overall-pct ${pct}`}>{Math.round(p.pct)}%</span>
        </div>
        {workTypes.length > 0 && (
          <div className="desk-row-rings">
            {workTypes.map((wt) => (
              <WorkTypeGauge key={wt.code} wt={wt} />
            ))}
          </div>
        )}
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
  const overallOver = isOver(totalNorm, totalFact, totalPct);

  // Итоги по 4 видам работ = сумма соответствующих долей по всем проектам.
  // Берём шаблон порядка/меток из первого проекта с разбивкой.
  const wtTemplate = projects.find((p) => (p.work_types?.length ?? 0) > 0)?.work_types ?? [];
  const totalWorkTypes: DeskWorkType[] = wtTemplate.map((tpl, i) => {
    let plan = 0;
    let fact = 0;
    for (const p of projects) {
      const wt = p.work_types?.[i];
      if (wt) {
        plan += wt.plan_hours;
        fact += wt.fact_hours;
      }
    }
    return {
      code: tpl.code,
      label: tpl.label,
      plan_hours: plan,
      fact_hours: fact,
      pct: plan > 0 ? (fact / plan) * 100 : (fact > 0 ? 100 : 0),
    };
  });
  const analystTotal = totalWorkTypes.find((wt) => wt.code === 'analyst');

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={projects.length === 0}
      emptyText="Нет проектов"
    >
      <div className="desk-tasks-summary">
        <div className="desk-tasks-summary-kpis">
          <div className="desk-tasks-summary-item">
            <span className="desk-tasks-summary-val">{projects.length}</span>
            <span className="desk-tasks-summary-unit">проектов</span>
          </div>
          <div className="desk-tasks-summary-item">
            <span className={`desk-tasks-summary-val${overallOver ? ' over' : ''}`}>
              {Math.round(totalFact)} / {Math.round(totalNorm)} ч
            </span>
            <span className="desk-tasks-summary-unit">всего факт / план</span>
            {analystTotal && (
              <span className="desk-ts-sub mono">
                Анализ {Math.round(analystTotal.fact_hours)} / {Math.round(analystTotal.plan_hours)} ч
              </span>
            )}
          </div>
          <div className="desk-tasks-summary-item">
            <span className={`desk-tasks-summary-val${overallOver ? ' over' : ''}`}>{totalPct}%</span>
            <span className="desk-tasks-summary-unit">загрузка</span>
          </div>
        </div>
        {totalWorkTypes.length > 0 && (
          <>
            <div className="desk-ts-divider" />
            <div className="desk-ts-rings">
              {totalWorkTypes.map((wt) => (
                <WorkTypeGauge key={wt.code} wt={wt} />
              ))}
            </div>
          </>
        )}
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
