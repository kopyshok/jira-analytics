import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Empty } from 'antd';
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import './roadmap.css';
import type { AssignmentOut, ConflictOut } from '../../../api/resourcePlanning';
import type { EmployeeResponse } from '../../../types/api';

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

const PHASE_COLORS: Record<string, string> = {
  analyst: 'rgba(105,177,255,0.75)',
  dev:     'rgba(179,127,235,0.75)',
  qa:      'rgba(149,222,100,0.75)',
  opo:     'rgba(255,169,64,0.75)',
};

const PHASE_LABELS: Record<string, string> = { analyst: 'Анализ', dev: 'Разработка', qa: 'Тестирование', opo: 'ОПЭ' };

const INIT_COLORS = [
  '#69b1ff', '#b37feb', '#95de64', '#ffa940', '#ff85c2',
  '#ff7875', '#36cfc9', '#b37feb', '#69b1ff', '#ffa940',
];

function parseDate(str: string): Date {
  const [y, m, d] = str.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function addDay(date: Date, n: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function formatGanttDate(date: Date): string {
  const d = String(date.getDate()).padStart(2, '0');
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const y = date.getFullYear();
  return `${y}-${m}-${d}`;
}

function quarterBounds(quarter: string, year: number): [Date, Date] {
  const q = parseInt(quarter.replace('Q', ''), 10) || 3;
  const startMonth = (q - 1) * 3;
  return [new Date(year, startMonth, 1), new Date(year, startMonth + 3, 1)];
}

function buildWeeks(qStart: Date, qEnd: Date): Array<{ label: string; month: string; num: string; start: Date; end: Date; index: number }> {
  const weeks = [];
  const d = new Date(qStart);
  // find first Monday
  const dow = d.getDay();
  const toMon = dow === 0 ? 1 : dow === 1 ? 0 : 8 - dow;
  d.setDate(d.getDate() + toMon);
  let i = 0;
  while (d < qEnd) {
    const end = new Date(d);
    end.setDate(end.getDate() + 6);
    weeks.push({
      index: i++,
      label: `${d.getDate()} ${MONTHS[d.getMonth()]}`,
      month: MONTHS[d.getMonth()],
      num: `${d.getDate()}–${end.getDate()}`,
      start: new Date(d),
      end,
    });
    d.setDate(d.getDate() + 7);
  }
  return weeks;
}

function pctClass(pct: number): string {
  if (pct > 100) return 'hc-over';
  if (pct >= 80) return 'hc-warn';
  if (pct > 0) return 'hc-ok';
  return 'hc-empty';
}

interface InitiativeInfo {
  id: string;
  key: string | null;
  name: string;
  color: string;
  weekStart: number;
  weekEnd: number;
  phases: Array<{ phase: string; start: string; end: string; hours: number | null; isCritical: boolean }>;
  employeeIds: string[];
}

interface Props {
  assignments: AssignmentOut[];
  conflicts: ConflictOut[]; // reserved for future conflict highlighting
  employees: EmployeeResponse[];
  quarter: string;
  year: number;
}

export default function RoadmapMode({ assignments, employees, quarter, year }: Props) {
  const drillGanttRef = useRef<HTMLDivElement>(null);
  const swimlanesRef = useRef<HTMLDivElement>(null);
  const weekHeadersRef = useRef<HTMLDivElement>(null);
  const sidebarListRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const customTipRef = useRef<HTMLDivElement>(null);

  const [drillOpen, setDrillOpen] = useState(false);
  const [drillTitle, setDrillTitle] = useState('—');
  const [drillMeta, setDrillMeta] = useState('');
  const [breadcrumb, setBreadcrumb] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState('');
  const [activeQuarter] = useState<string>(`${quarter} ${year}`);

  const drillGanttInit = useRef(false);

  const [qStart, qEnd] = useMemo(() => quarterBounds(quarter, year), [quarter, year]);
  const weeks = useMemo(() => buildWeeks(qStart, qEnd), [qStart, qEnd]);

  const validAssignments = useMemo(
    () => assignments.filter(a => a.start_date && a.end_date),
    [assignments]
  );

  // Build initiative info from assignments
  const initiatives = useMemo((): InitiativeInfo[] => {
    const map = new Map<string, InitiativeInfo>();
    let colorIdx = 0;
    for (const a of validAssignments) {
      if (!map.has(a.backlog_item_id)) {
        map.set(a.backlog_item_id, {
          id: a.backlog_item_id,
          key: a.backlog_item_key,
          name: a.backlog_item_title,
          color: INIT_COLORS[colorIdx++ % INIT_COLORS.length],
          weekStart: Infinity,
          weekEnd: -Infinity,
          phases: [],
          employeeIds: [],
        });
      }
      const info = map.get(a.backlog_item_id)!;
      info.phases.push({
        phase: a.phase,
        start: a.start_date!,
        end: a.end_date!,
        hours: a.hours_allocated,
        isCritical: a.is_on_critical_path,
      });
      if (a.employee_id && !info.employeeIds.includes(a.employee_id)) {
        info.employeeIds.push(a.employee_id);
      }
      // Map to week indices
      const aStart = parseDate(a.start_date!);
      const aEnd = parseDate(a.end_date!);
      const numWeeks = weeks.length || 1;
      const qStartMs = qStart.getTime();
      const qDuration = qEnd.getTime() - qStartMs;
      const wStart = Math.max(0, Math.floor(((aStart.getTime() - qStartMs) / qDuration) * numWeeks));
      const wEnd = Math.min(numWeeks - 1, Math.ceil(((aEnd.getTime() - qStartMs) / qDuration) * numWeeks));
      info.weekStart = Math.min(info.weekStart, wStart);
      info.weekEnd = Math.max(info.weekEnd, wEnd);
    }
    for (const info of map.values()) {
      if (!isFinite(info.weekStart)) info.weekStart = 0;
      if (!isFinite(info.weekEnd)) info.weekEnd = 0;
    }
    return Array.from(map.values());
  }, [validAssignments, weeks, qStart, qEnd]);

  const showTip = useCallback((e: MouseEvent, init: InitiativeInfo) => {
    const tip = customTipRef.current;
    if (!tip) return;
    const startW = weeks[Math.min(init.weekStart, weeks.length - 1)];
    const endW = weeks[Math.min(init.weekEnd, weeks.length - 1)];
    tip.querySelector('.custom-tip-name')!.textContent = init.name;
    const rows = tip.querySelectorAll('.custom-tip-row b');
    if (rows[0]) rows[0].textContent = startW ? `${startW.label} – ${endW?.label ?? ''}` : '—';
    if (rows[1]) rows[1].textContent = `${init.phases.length} фаз`;
    if (rows[2]) rows[2].textContent = `${init.employeeIds.length} сотрудников`;
    tip.style.display = 'block';
    tip.style.left = `${e.clientX + 12}px`;
    tip.style.top = `${e.clientY - 30}px`;
  }, [weeks]);

  const hideTip = useCallback(() => {
    if (customTipRef.current) customTipRef.current.style.display = 'none';
  }, []);

  const loadDrillGantt = useCallback((init: InitiativeInfo) => {
    const container = drillGanttRef.current;
    if (!container) return;

    const phases = init.phases;
    if (phases.length === 0) return;
    const earliest = phases.reduce((m, p) => p.start < m ? p.start : m, phases[0].start);
    const latest = phases.reduce((m, p) => p.end > m ? p.end : m, phases[0].end);
    const dStart = parseDate(earliest); dStart.setDate(dStart.getDate() - 3);
    const dEnd = parseDate(latest); dEnd.setDate(dEnd.getDate() + 7);

    if (!drillGanttInit.current) {
      gantt.config.readonly = true;
      gantt.config.drag_links = false;
      gantt.config.drag_move = false;
      gantt.config.drag_resize = false;
      gantt.config.scale_height = 46;
      gantt.config.row_height = 28;
      gantt.config.bar_height = 18;
      (gantt.config as any).link_arrow_size = 6;
      gantt.config.date_format = '%Y-%m-%d';

      gantt.config.layout = {
        css: 'gantt_container',
        rows: [{
          cols: [
            { view: 'grid', id: 'grid', width: 260, scrollX: 'scrollHor', scrollY: 'scrollVer' },
            { resizer: true, width: 1 },
            { view: 'timeline', id: 'timeline', scrollX: 'scrollHor', scrollY: 'scrollVer' },
            { view: 'scrollbar', id: 'scrollVer', group: 'vertical' },
          ],
        }, { view: 'scrollbar', id: 'scrollHor', group: 'horizontal' }],
      } as any;

      gantt.config.columns = [
        {
          name: 'text', label: 'Фаза', width: 210, tree: true,
          template: (task: any) => task.isMilestone ? `<span style="color:#ff4d4f;font-weight:600">◆ ${task.text}</span>` : task.text,
        },
        {
          name: 'duration', label: 'Дн', width: 38, align: 'center',
          template: (task: any) => task.type === (gantt.config as any).types?.milestone ? '' : task.duration,
        },
      ] as any;

      gantt.config.scales = [
        { unit: 'month', step: 1, format: '%F %Y' },
        { unit: 'week', step: 1, format: (date: Date) => `${date.getDate()} ${MONTHS[date.getMonth()]}` },
      ] as any;

      gantt.templates.task_class = (_s: any, _e: any, task: any) => task.isCritical ? 'gantt-critical' : '';
      gantt.templates.task_text = (_s: any, _e: any, task: any) => {
        const milestoneType = (gantt.config as any).types?.milestone;
        return task.type === milestoneType ? '' : task.text;
      };
      gantt.templates.tooltip_text = (_s: any, _e: any, task: any) => {
        const milestoneType = (gantt.config as any).types?.milestone;
        if (task.type === milestoneType) return `<b>${task.text}</b>`;
        return `<b>${task.text}</b><br>Роль: ${PHASE_LABELS[task.phaseType] ?? '—'}`;
      };

      gantt.config.start_date = dStart;
      gantt.config.end_date = dEnd;
      gantt.init(container);
      drillGanttInit.current = true;
    } else {
      gantt.config.start_date = dStart;
      gantt.config.end_date = dEnd;
      gantt.clearAll();
      gantt.render();
    }

    const tasks: any[] = [];
    const links: any[] = [];
    const phaseOrder = ['analyst', 'dev', 'qa', 'opo'];

    // Group phases by role
    const phasesByRole = new Map<string, typeof phases>();
    for (const p of phases) {
      if (!phasesByRole.has(p.phase)) phasesByRole.set(p.phase, []);
      phasesByRole.get(p.phase)!.push(p);
    }

    let taskId = 1;
    const phaseGroupIds: Record<string, number> = {};
    for (const roleId of phaseOrder) {
      const rolePhases = phasesByRole.get(roleId);
      if (!rolePhases) continue;
      const groupId = taskId++;
      phaseGroupIds[roleId] = groupId;
      const minStart = rolePhases.reduce((m, p) => p.start < m ? p.start : m, rolePhases[0].start);
      const maxEnd = rolePhases.reduce((m, p) => p.end > m ? p.end : m, rolePhases[0].end);
      const hasCritical = rolePhases.some(p => p.isCritical);
      tasks.push({
        id: groupId,
        text: PHASE_LABELS[roleId] ?? roleId,
        start_date: minStart,
        end_date: formatGanttDate(addDay(parseDate(maxEnd), 1)),
        isCritical: hasCritical,
        color: hasCritical ? 'rgba(255,77,79,0.85)' : PHASE_COLORS[roleId] ?? '#888',
        phaseType: roleId,
        progress: 0,
      });
    }

    // Add phase-order links
    const roleOrder2 = phaseOrder.filter(r => phaseGroupIds[r] !== undefined);
    for (let i = 1; i < roleOrder2.length; i++) {
      links.push({
        id: links.length + 1,
        source: phaseGroupIds[roleOrder2[i - 1]],
        target: phaseGroupIds[roleOrder2[i]],
        type: '0',
      });
    }

    // Milestone at end
    const lastCritPhase = [...phases]
      .filter(p => p.isCritical)
      .sort((a, b) => b.end.localeCompare(a.end))[0] ?? phases[phases.length - 1];

    if (lastCritPhase) {
      const msDate = parseDate(lastCritPhase.end);
      msDate.setDate(msDate.getDate() + 1);
      const msId = taskId++;
      tasks.push({
        id: msId,
        text: 'Завершение',
        start_date: formatGanttDate(msDate),
        end_date: formatGanttDate(addDay(msDate, 1)),
        type: (gantt.config as any).types?.milestone ?? 'milestone',
        isMilestone: true,
        color: '#ff4d4f',
      });
      // link from last role group
      const lastRoleId = roleOrder2[roleOrder2.length - 1];
      if (phaseGroupIds[lastRoleId]) {
        links.push({ id: links.length + 1, source: phaseGroupIds[lastRoleId], target: msId, type: '0' });
      }
    }

    gantt.parse({ data: tasks, links });
  }, []);

  const openDrill = useCallback((id: string) => {
    const init = initiatives.find(x => x.id === id);
    if (!init) return;
    setDrillTitle(init.name);
    const startW = weeks[Math.min(init.weekStart, weeks.length - 1)];
    const endW = weeks[Math.min(init.weekEnd, weeks.length - 1)];
    const dateRange = startW ? `${startW.label} – ${endW?.label ?? ''}` : '';
    setDrillMeta(`${dateRange} · ${init.employeeIds.length} сотрудников`);
    setBreadcrumb(init.name);
    setDrillOpen(true);
    sidebarListRef.current?.querySelectorAll('.init-card').forEach(c => c.classList.remove('active'));
    sidebarListRef.current?.querySelector(`#card-${id.replace(/[^a-z0-9]/gi, '_')}`)?.classList.add('active');
    setTimeout(() => loadDrillGantt(init), drillGanttInit.current ? 50 : 100);
  }, [initiatives, weeks, loadDrillGantt]);

  const closeDrill = useCallback(() => {
    setDrillOpen(false);
    setBreadcrumb(null);
    sidebarListRef.current?.querySelectorAll('.init-card').forEach(c => c.classList.remove('active'));
    try { gantt.clearAll(); } catch { /* ignore */ }
    drillGanttInit.current = false;
  }, []);

  // Build week headers
  useEffect(() => {
    const container = weekHeadersRef.current;
    if (!container) return;
    container.innerHTML = '';
    weeks.forEach((w, i) => {
      const el = document.createElement('div');
      el.className = 'week-col' + (i === 0 ? ' current-week' : '');
      el.innerHTML = `<div class="wc-month">${w.month}</div><div class="wc-num">${w.num}</div>`;
      container.appendChild(el);
    });
  }, [weeks]);

  // Build swimlanes
  useEffect(() => {
    const container = swimlanesRef.current;
    if (!container) return;
    container.innerHTML = '';

    const ROLES = [
      { id: 'analyst', label: 'Аналитики',    cls: 'analyst', color: '#69b1ff' },
      { id: 'dev',     label: 'Разработчики',  cls: 'dev',     color: '#b37feb' },
      { id: 'qa',      label: 'Тестировщики',  cls: 'qa',      color: '#95de64' },
      { id: 'opo',     label: 'ОПЭ',           cls: 'ope',     color: '#ffa940' },
    ];

    // Compute per-role heatmap from real assignments
    const numWeeks = weeks.length;
    const roleHeatmap: Record<string, number[]> = {};
    for (const role of ROLES) {
      roleHeatmap[role.id] = Array(numWeeks).fill(0);
      const roleEmps = employees.filter(e => {
        const r = (e.role ?? '').toLowerCase();
        if (role.id === 'analyst') return r.includes('analyst') || r.includes('аналитик');
        if (role.id === 'qa') return r.includes('qa') || r.includes('тест') || r.includes('test');
        if (role.id === 'opo') return r.includes('ope') || r.includes('опэ');
        return !r.includes('analyst') && !r.includes('аналитик') && !r.includes('qa') && !r.includes('тест') && !r.includes('test') && !r.includes('ope') && !r.includes('опэ');
      });
      const capacity = roleEmps.length * 5 * 8 || 40; // default 40h if no employees
      const roleAssignments = validAssignments.filter(a => a.phase === role.id && a.hours_allocated);
      weeks.forEach((w, wi) => {
        const weekEndD = new Date(w.start);
        weekEndD.setDate(weekEndD.getDate() + 7);
        let totalH = 0;
        for (const a of roleAssignments) {
          const aStart = parseDate(a.start_date!);
          const aEnd = parseDate(a.end_date!);
          if (aStart >= weekEndD || aEnd <= w.start) continue;
          const totalDays = Math.max(1, (aEnd.getTime() - aStart.getTime()) / 86400000);
          const overlapStart = aStart > w.start ? aStart : w.start;
          const overlapEnd = aEnd < weekEndD ? aEnd : weekEndD;
          const overlapDays = Math.max(0, (overlapEnd.getTime() - overlapStart.getTime()) / 86400000);
          totalH += (a.hours_allocated! * overlapDays) / totalDays;
        }
        roleHeatmap[role.id][wi] = Math.round((totalH / capacity) * 100);
      });
    }

    // Build role→initiatives map
    const roleInitiatives: Record<string, InitiativeInfo[]> = { analyst: [], dev: [], qa: [], opo: [] };
    for (const init of initiatives) {
      const roleSet = new Set(init.phases.map(p => p.phase));
      for (const r of roleSet) {
        if (roleInitiatives[r]) roleInitiatives[r].push(init);
      }
    }

    ROLES.forEach(role => {
      const lane = document.createElement('div');
      lane.className = 'swimlane';

      const roleCol = document.createElement('div');
      roleCol.className = 'swimlane-role-col';
      const empCount = employees.filter(e => {
        const r = (e.role ?? '').toLowerCase();
        if (role.id === 'analyst') return r.includes('analyst') || r.includes('аналитик');
        if (role.id === 'qa') return r.includes('qa') || r.includes('тест') || r.includes('test');
        if (role.id === 'opo') return r.includes('ope') || r.includes('опэ');
        return !r.includes('analyst') && !r.includes('аналитик') && !r.includes('qa') && !r.includes('тест') && !r.includes('test') && !r.includes('ope') && !r.includes('опэ');
      }).length;
      const capacity = empCount * 40 * 13; // total q capacity
      roleCol.innerHTML = `
        <div class="role-badge ${role.cls}">${role.label}</div>
        <div class="role-meta"><b>${empCount}</b> чел · <b>${capacity}</b> ч/кв</div>
      `;
      lane.appendChild(roleCol);

      const chart = document.createElement('div');
      chart.className = 'swimlane-chart';

      const heatRow = document.createElement('div');
      heatRow.className = 'heatmap-row';
      (roleHeatmap[role.id] || []).forEach((pct, i) => {
        const cell = document.createElement('div');
        cell.className = 'heatmap-cell ' + pctClass(pct);
        cell.setAttribute('data-pct', String(pct));
        cell.title = `Нед ${i + 1}: ${pct}%`;
        heatRow.appendChild(cell);
      });
      chart.appendChild(heatRow);

      const initRow = document.createElement('div');
      initRow.className = 'initiatives-row';

      const roleInits = roleInitiatives[role.id] ?? [];
      const layoutRows: InitiativeInfo[][] = [];
      roleInits.forEach(init => {
        let placed = false;
        for (const row of layoutRows) {
          const last = row[row.length - 1];
          if (last.weekEnd < init.weekStart) { row.push(init); placed = true; break; }
        }
        if (!placed) layoutRows.push([init]);
      });

      layoutRows.forEach((rowInits, rowIdx) => {
        rowInits.forEach(init => {
          const numW = numWeeks || 13;
          const bar = document.createElement('div');
          bar.className = 'init-bar';
          bar.style.left = `${(init.weekStart / numW) * 100}%`;
          bar.style.width = `${Math.max(5, ((init.weekEnd - init.weekStart + 1) / numW) * 100)}%`;
          bar.style.background = init.color + 'cc';
          bar.style.color = '#141414';
          bar.style.top = rowIdx === 0 ? '6px' : '30px';
          bar.textContent = init.key ?? init.name;
          bar.title = init.name;
          bar.addEventListener('click', () => openDrill(init.id));
          bar.addEventListener('mousemove', (e) => showTip(e as MouseEvent, init));
          bar.addEventListener('mouseleave', hideTip);
          initRow.appendChild(bar);
        });
      });

      chart.appendChild(initRow);
      lane.appendChild(chart);
      container.appendChild(lane);
    });
  }, [initiatives, employees, validAssignments, weeks, openDrill, showTip, hideTip]);

  // Sidebar cards
  const renderSidebarCards = useCallback((inits: InitiativeInfo[]) => {
    const list = sidebarListRef.current;
    if (!list) return;
    list.innerHTML = '';
    inits.forEach((init, idx) => {
      const card = document.createElement('div');
      card.className = 'init-card';
      card.id = `card-${init.id.replace(/[^a-z0-9]/gi, '_')}`;
      (card as HTMLElement).style.animationDelay = `${idx * 0.04}s`;
      const startW = weeks[Math.min(init.weekStart, weeks.length - 1)];
      const endW = weeks[Math.min(init.weekEnd, weeks.length - 1)];
      const dateRange = startW ? `${startW.label} – ${endW?.label ?? ''}` : '—';
      const phaseCount = new Set(init.phases.map(p => p.phase)).size;
      card.innerHTML = `
        <div class="init-card-name">${init.name}</div>
        <div class="init-card-meta">
          <div class="init-card-dates">${dateRange}</div>
          <div class="init-card-status status-active">${phaseCount} фаз</div>
        </div>
        <button class="drill-btn" data-id="${init.id}">Детали ›</button>
      `;
      card.addEventListener('click', () => openDrill(init.id));
      list.appendChild(card);
    });
  }, [initiatives, weeks, openDrill]);

  useEffect(() => {
    renderSidebarCards(initiatives);
  }, [renderSidebarCards, initiatives]);

  useEffect(() => {
    if (!searchQ.trim()) { renderSidebarCards(initiatives); return; }
    const filtered = initiatives.filter(i => i.name.toLowerCase().includes(searchQ.toLowerCase()));
    renderSidebarCards(filtered);
  }, [searchQ, renderSidebarCards, initiatives]);

  useEffect(() => {
    return () => {
      try { gantt.clearAll(); } catch { /* ignore */ }
      drillGanttInit.current = false;
    };
  }, []);

  if (validAssignments.length === 0) {
    return (
      <div className="dhtmlx-roadmap-mode">
        <Empty description="Нет данных для отображения" style={{ paddingTop: 80, color: '#8c8c8c' }} />
      </div>
    );
  }

  return (
    <div className="dhtmlx-roadmap-mode">
      {/* Header */}
      <header className="app-header">
        <div className="header-logo">RPM<span>·</span>Plan</div>
        <div className="header-sep" />
        <div className="breadcrumb">
          {breadcrumb ? (
            <>
              <span style={{ cursor: 'pointer', color: 'var(--text-muted)' }} onClick={closeDrill}>Roadmap</span>
              <span className="crumb-sep">›</span>
              <span className="crumb-active">{breadcrumb}</span>
            </>
          ) : (
            <span className="crumb-active">Roadmap</span>
          )}
        </div>
        <div className="header-spacer" />
        <div className="legend-pills">
          <div className="legend-pill"><div className="legend-dot" style={{ background: 'var(--load-ok)' }}></div><span>&lt;80%</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background: 'var(--load-warn)' }}></div><span>80–100%</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background: 'var(--load-over)' }}></div><span>&gt;100%</span></div>
          <div className="header-sep" />
          <div className="legend-pill"><div className="legend-dot" style={{ background: 'var(--analyst)' }}></div><span>Аналитик</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background: 'var(--dev)' }}></div><span>Разработчик</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background: 'var(--qa)' }}></div><span>QA</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background: 'var(--ope)' }}></div><span>ОПЭ</span></div>
        </div>
        <div className="header-sep" />
        <div className="quarter-switcher">
          <button className="quarter-btn active">{activeQuarter}</button>
        </div>
      </header>

      {/* Main layout */}
      <div className="main-layout">
        <div className="roadmap-area">
          <div className="swimlane-header">
            <div className="swimlane-header-role">Роль / Команда</div>
            <div className="week-headers" ref={weekHeadersRef}></div>
          </div>
          <div className="swimlanes-container" ref={swimlanesRef}></div>
        </div>

        <div className="sidebar">
          <div className="sidebar-header">
            <div className="sidebar-title">Инициативы · {quarter} {year}</div>
            <input
              className="sidebar-search"
              type="text"
              placeholder="Поиск инициативы…"
              ref={searchRef}
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
            />
          </div>
          <div className="sidebar-list" ref={sidebarListRef}></div>
        </div>
      </div>

      {/* Drill-down panel */}
      <div className={`drill-panel${drillOpen ? ' open' : ''}`}>
        <div className="drill-header">
          <button className="drill-close" onClick={closeDrill} title="Закрыть">✕</button>
          <div className="drill-title">{drillTitle}</div>
          <div className="drill-meta">{drillMeta}</div>
          <div className="drill-legend">
            <div className="dl-item"><div className="dl-swatch" style={{ background: 'rgba(105,177,255,0.7)' }}></div>Анализ</div>
            <div className="dl-item"><div className="dl-swatch" style={{ background: 'rgba(179,127,235,0.7)' }}></div>Разработка</div>
            <div className="dl-item"><div className="dl-swatch" style={{ background: 'rgba(149,222,100,0.7)' }}></div>Тестирование</div>
            <div className="dl-item"><div className="dl-swatch" style={{ background: 'rgba(255,169,64,0.7)' }}></div>ОПЭ</div>
            <div className="dl-item"><div className="dl-critical"></div>Критический путь</div>
          </div>
        </div>
        <div className="drill-body">
          <div id="drill-gantt-container-roadmap" ref={drillGanttRef}></div>
        </div>
      </div>

      {/* Custom tooltip */}
      <div className="custom-tip" ref={customTipRef}>
        <div className="custom-tip-name"></div>
        <div className="custom-tip-row"><span>Период</span><b></b></div>
        <div className="custom-tip-row"><span>Фаз</span><b></b></div>
        <div className="custom-tip-row"><span>Сотрудников</span><b></b></div>
      </div>
    </div>
  );
}
