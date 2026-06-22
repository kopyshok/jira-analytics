import { useState } from 'react';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import type {
  CategoryBreakdownData,
  WorkTypeCategory,
  WorkTypeIssue,
  WorkTypeSlice,
} from '../../types/desk';

/** Класс по нагрузке: >110 перегруз, 70–110 норма, <70 недогруз. */
function loadClass(wt: WorkTypeSlice): { chip: string; fill: string } {
  const overZeroPlan = wt.plan_hours === 0 && wt.fact_hours > 0;
  if (overZeroPlan || wt.pct > 110) return { chip: 'desk-chip-over', fill: 'var(--red)' };
  if (wt.pct >= 70) return { chip: 'desk-chip-ok', fill: 'var(--green)' };
  return { chip: 'desk-chip-low', fill: 'var(--accent-dim)' };
}

function IssueRow({ iss }: { iss: WorkTypeIssue }) {
  const label = `${iss.key ? `${iss.key} · ` : ''}${iss.title ?? '—'}`;
  return (
    <div className="desk-cat-issue">
      <span className="desk-cat-issue-name">
        {iss.jira_url ? (
          <a href={iss.jira_url} target="_blank" rel="noreferrer">{label}</a>
        ) : label}
      </span>
      <span className="desk-cat-issue-hrs">{Math.round(iss.fact_hours)} ч</span>
    </div>
  );
}

function CategoryRow({ cat }: { cat: WorkTypeCategory }) {
  const [open, setOpen] = useState(false);
  const hasIssues = cat.issues.length > 0;
  return (
    <div className="desk-cat-block">
      <button
        type="button"
        className="desk-cat-head"
        onClick={() => hasIssues && setOpen((o) => !o)}
        disabled={!hasIssues}
      >
        <span className={`desk-tree-chevron${open ? ' open' : ''}${hasIssues ? '' : ' hidden'}`}>▸</span>
        <span className="desk-cat-dot" style={{ background: cat.color }} />
        <span className="desk-cat-label">{cat.label}</span>
        <span className="desk-cat-count">{cat.issues.length}</span>
        <span className="desk-cat-hrs">{Math.round(cat.fact_hours)} ч</span>
      </button>
      {open && (
        <div className="desk-cat-issues">
          {cat.issues.map((iss, i) => (
            <IssueRow key={`${iss.key ?? ''}-${i}`} iss={iss} />
          ))}
        </div>
      )}
    </div>
  );
}

function WorkTypeRow({ wt }: { wt: WorkTypeSlice }) {
  const [open, setOpen] = useState(false);
  const overZeroPlan = wt.plan_hours === 0 && wt.fact_hours > 0;
  const { chip, fill } = loadClass(wt);
  const scaleMax = Math.max(wt.plan_hours, wt.fact_hours, 1);
  const fillW = Math.min(100, (wt.fact_hours / scaleMax) * 100);
  const tickLeft = overZeroPlan ? 100 : Math.min(100, (wt.plan_hours / scaleMax) * 100);
  const hasCats = wt.categories.length > 0;

  return (
    <div className="desk-bullet-item">
      <button
        type="button"
        className="desk-bullet-header desk-wt-head"
        onClick={() => hasCats && setOpen((o) => !o)}
        disabled={!hasCats}
      >
        <span className={`desk-tree-chevron${open ? ' open' : ''}${hasCats ? '' : ' hidden'}`}>▸</span>
        <span className="desk-bullet-label">{wt.label}</span>
        <span className="desk-bullet-nums">
          {Math.round(wt.fact_hours)} ч / {Math.round(wt.plan_hours)} ч
          <span className={`desk-pct-chip ${chip}`}>{Math.round(wt.pct)}%</span>
        </span>
      </button>
      <div className="desk-bullet-track">
        <div className="desk-bullet-fill" style={{ width: `${fillW}%`, background: fill }} />
        <div className="desk-bullet-tick" style={{ left: `${tickLeft}%` }} />
      </div>
      {open && (
        <div className="desk-wt-cats">
          {wt.categories.map((cat, i) => (
            <CategoryRow key={`${cat.label}-${i}`} cat={cat} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function CategoryBreakdownWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<CategoryBreakdownData>(token, 'category_breakdown');
  const workTypes = data?.work_types ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={workTypes.length === 0}
    >
      <div className="desk-bullet-list">
        {workTypes.map((wt) => (
          <WorkTypeRow key={wt.label} wt={wt} />
        ))}
      </div>
    </WidgetShell>
  );
}
