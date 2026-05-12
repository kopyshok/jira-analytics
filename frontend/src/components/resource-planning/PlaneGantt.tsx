import { useMemo, useState } from 'react';
import type { AssignmentOut, ScheduledBlock, EmployeeLoadOut } from '../../api/resourcePlanning';
import type { EmployeeResponse } from '../../types/api';
import { quarterBounds } from '../../utils/gantt';
import PlaneSidebar, { type PlaneFilters } from './PlaneSidebar';
import css from './PlaneGantt.module.css';

interface Props {
  assignments: AssignmentOut[];
  blocks: ScheduledBlock[];
  employees: EmployeeResponse[];
  employeeLoad?: EmployeeLoadOut[];
  quarter: string;
  year: number;
  planLabel?: string | null;
  onAssignmentClick: (id: string) => void;
}

// Deterministic avatar color per name
const AVATAR_COLORS = [
  '#6366f1', '#10b981', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316',
];

function avatarColor(name: string | null): string {
  if (!name) return '#52525b';
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function initials(name: string | null): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

const PHASE_ROLE_MAP: Record<string, string> = {
  analyst: 'analyst',
  dev: 'dev',
  qa: 'qa',
  opo: 'opo',
};

const RU_MONTHS_SHORT = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

type WeekEntry = {
  label: string;
  leftPct: number;
  widthPct: number;
  isTodayWeek: boolean;
};

type MonthGroup = {
  label: string;
  weeks: WeekEntry[];
};

function buildWeekGroups(start: Date, end: Date): MonthGroup[] {
  const totalMs = end.getTime() - start.getTime();

  // Collect weeks
  const d = new Date(start);
  // Snap to Monday
  const dow = d.getDay();
  if (dow !== 1) d.setDate(d.getDate() - ((dow + 6) % 7));

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const allWeeks: WeekEntry[] = [];
  let weekNum = 1;
  while (d <= end) {
    const wStart = new Date(d);
    const wEnd = new Date(d);
    wEnd.setDate(wEnd.getDate() + 6);

    const clampStart = wStart < start ? new Date(start) : wStart;
    const clampEnd = wEnd > end ? new Date(end) : wEnd;

    const leftMs = clampStart.getTime() - start.getTime();
    const widthMs = clampEnd.getTime() - clampStart.getTime() + 86_400_000;
    const leftPct = (leftMs / totalMs) * 100;
    const widthPct = (widthMs / totalMs) * 100;

    const isTodayWeek = today >= clampStart && today <= clampEnd;

    allWeeks.push({
      label: `Н${weekNum}`,
      leftPct,
      widthPct,
      isTodayWeek,
    });

    d.setDate(d.getDate() + 7);
    weekNum++;
    if (weekNum > 16) break; // safety
  }

  // Group weeks by dominant month
  const monthMap = new Map<string, WeekEntry[]>();
  for (const w of allWeeks) {
    // Find midpoint of week
    const midPct = w.leftPct + w.widthPct / 2;
    const midMs = (midPct / 100) * totalMs;
    const midDate = new Date(start.getTime() + midMs);
    const monthKey = `${midDate.getFullYear()}-${midDate.getMonth()}`;
    if (!monthMap.has(monthKey)) monthMap.set(monthKey, []);
    monthMap.get(monthKey)!.push(w);
  }

  return Array.from(monthMap.entries()).map(([key, weeks]) => {
    const [, monthIdx] = key.split('-').map(Number);
    return { label: RU_MONTHS_SHORT[monthIdx] ?? '', weeks };
  });
}

function dateToBarPct(dateStr: string | null, start: Date, totalMs: number): number {
  if (!dateStr) return 0;
  const d = new Date(dateStr + 'T00:00:00');
  return Math.max(0, Math.min(100, ((d.getTime() - start.getTime()) / totalMs) * 100));
}

export default function PlaneGantt({
  assignments,
  employees,
  employeeLoad,
  quarter,
  year,
  planLabel,
  onAssignmentClick,
}: Props) {
  const [filters, setFilters] = useState<PlaneFilters>({
    projects: [],
    employees: [],
    roles: [],
    status: [],
  });

  const { start: qStart, end: qEnd } = useMemo(() => quarterBounds(quarter, year), [quarter, year]);
  const totalMs = qEnd.getTime() - qStart.getTime() + 86_400_000;

  const monthGroups = useMemo(() => buildWeekGroups(qStart, qEnd), [qStart, qEnd]);

  // Derive project list from assignments
  const projects = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of assignments) {
      const key = a.backlog_item_key?.split('-')[0] ?? 'N/A';
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => b.count - a.count);
  }, [assignments]);

  // Employees who have at least one assignment in quarter
  const activeEmployeeIds = useMemo(() => {
    const ids = new Set<string>();
    for (const a of assignments) {
      if (a.employee_id) ids.add(a.employee_id);
    }
    return ids;
  }, [assignments]);

  // Build overload set from employeeLoad
  const overloadedIds = useMemo(() => {
    const ids = new Set<string>();
    if (!employeeLoad) return ids;
    for (const row of employeeLoad) {
      const hasOverload = row.days.some(d => d.pct > 1.1);
      if (hasOverload) ids.add(row.employee_id);
    }
    return ids;
  }, [employeeLoad]);

  // Filter employees
  const displayEmployees = useMemo(() => {
    let list = employees.filter(e => activeEmployeeIds.has(e.id));

    // If employee filter is set, also show explicitly selected employees
    if (filters.employees.length > 0) {
      const selected = filters.employees;
      list = employees.filter(e => activeEmployeeIds.has(e.id) || selected.includes(e.id));
      list = list.filter(e => selected.includes(e.id));
    }

    return list;
  }, [employees, activeEmployeeIds, filters.employees]);

  // Filter assignments
  const filteredAssignments = useMemo(() => {
    let list = assignments;

    if (filters.projects.length > 0) {
      list = list.filter(a => {
        const key = a.backlog_item_key?.split('-')[0] ?? 'N/A';
        return filters.projects.includes(key);
      });
    }
    if (filters.roles.length > 0) {
      list = list.filter(a => filters.roles.includes(PHASE_ROLE_MAP[a.phase] ?? a.phase));
    }

    return list;
  }, [assignments, filters.projects, filters.roles]);

  // Today line position
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayPct = dateToBarPct(today.toISOString().slice(0, 10), qStart, totalMs);
  const showTodayLine = today >= qStart && today <= qEnd;

  // Period chip
  const qStartFmt = `${qStart.getDate()} ${RU_MONTHS_SHORT[qStart.getMonth()]}`;
  const qEndFmt = `${qEnd.getDate()} ${RU_MONTHS_SHORT[qEnd.getMonth()]} ${year}`;

  return (
    <div className={css.shell}>
      {/* Header */}
      <div className={css.header}>
        <div className={css.breadcrumb}>
          <span>Планирование</span>
          <span>{quarter} {year}</span>
          {planLabel && <span>{planLabel}</span>}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={css.periodChip}>{qStartFmt} — {qEndFmt}</span>
        </div>
      </div>

      {/* Body */}
      <div className={css.body}>
        <PlaneSidebar
          employees={employees.filter(e => activeEmployeeIds.has(e.id))}
          projects={projects}
          filters={filters}
          quarter={quarter}
          year={year}
          onChange={setFilters}
        />

        <div className={css.main}>
          {/* Toolbar */}
          <div className={css.toolbar}>
            <button
              type="button"
              className={css.todayBtn}
              onClick={() => {
                const el = document.getElementById('plane-today-line');
                el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
              }}
            >
              Сегодня
            </button>
            <span className={css.toolbarSpacer} />
            <button type="button" className={css.zoomBtn} title="Увеличить масштаб">+</button>
            <button type="button" className={css.zoomBtn} title="Уменьшить масштаб">−</button>
          </div>

          {/* Grid */}
          <div className={css.gridWrapper}>
            {/* Grid header */}
            <div className={css.gridHeader}>
              <div className={css.leftColHeader}>Сотрудник</div>
              <div className={css.weekColumns}>
                {monthGroups.map(mg => (
                  <div key={mg.label} className={css.monthGroup}>
                    <div className={css.monthLabel}>{mg.label}</div>
                    <div className={css.weekCells}>
                      {mg.weeks.map(w => (
                        <div
                          key={w.label}
                          className={`${css.weekCell}${w.isTodayWeek ? ` ${css.today}` : ''}`}
                        >
                          {w.label}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Rows */}
            <div className={css.rows}>
              {showTodayLine && (
                <div
                  id="plane-today-line"
                  className={css.todayLine}
                  style={{ left: `calc(240px + ${todayPct}%)` }}
                >
                  <div className={css.todayDot} />
                </div>
              )}

              {displayEmployees.length === 0 && (
                <div className={css.emptyState}>
                  <span className={css.emptyIcon}>📋</span>
                  <span>Нет назначений для отображения</span>
                  {(filters.employees.length > 0 || filters.projects.length > 0 || filters.roles.length > 0) && (
                    <button
                      type="button"
                      className={css.resetLink}
                      onClick={() => setFilters({ projects: [], employees: [], roles: [], status: [] })}
                    >
                      Сбросить фильтры
                    </button>
                  )}
                </div>
              )}

              {displayEmployees.map(emp => {
                const empAssignments = filteredAssignments.filter(
                  a => a.employee_id === emp.id && a.start_date && a.end_date,
                );
                const isOverloaded = overloadedIds.has(emp.id);

                return (
                  <div
                    key={emp.id}
                    className={`${css.row}${isOverloaded ? ` ${css.overload}` : ''}`}
                  >
                    <div className={css.empCol}>
                      <div
                        className={css.avatar}
                        style={{ background: avatarColor(emp.display_name) }}
                        title={emp.display_name}
                      >
                        {initials(emp.display_name)}
                      </div>
                      <div className={css.empInfo}>
                        <span className={css.empName}>{emp.display_name}</span>
                        {emp.role && <span className={css.empMeta}>{emp.role}</span>}
                      </div>
                      {isOverloaded && (
                        <span className={css.overloadIcon} title="Перегрузка">▲</span>
                      )}
                    </div>

                    <div className={css.barTrack}>
                      {empAssignments.map(a => {
                        const leftPct = dateToBarPct(a.start_date, qStart, totalMs);
                        const endPct = dateToBarPct(a.end_date, qStart, totalMs);
                        const widthPct = Math.max(endPct - leftPct, 0.5);
                        const roleClass = css[a.phase as keyof typeof css] ?? css.analyst;
                        const label = a.backlog_item_title;

                        return (
                          <div
                            key={a.id}
                            className={`${css.bar} ${roleClass}`}
                            style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                            title={`${label} — ${a.hours_allocated?.toFixed(0) ?? '?'} ч`}
                            onClick={() => onAssignmentClick(a.id)}
                          >
                            {label}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
