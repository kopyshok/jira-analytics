import { useEffect, useRef, useState, useMemo } from 'react';
import { Empty } from 'antd';
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import './classic.css';
import type { AssignmentOut, ConflictOut } from '../../../api/resourcePlanning';
import type { EmployeeResponse } from '../../../types/api';

const COLORS = {
  analyst: '#5b8dee',
  dev:     '#36cfc9',
  qa:      '#9254de',
  opo:     '#fa8c16',
  summary: '#3a4a5a',
};

/** Quarter string like 'Q3' → [startDate, endDate] for given year */
function quarterBounds(quarter: string, year: number): [Date, Date] {
  const q = parseInt(quarter.replace('Q', ''), 10) || 3;
  const startMonth = (q - 1) * 3;
  return [new Date(year, startMonth, 1), new Date(year, startMonth + 3, 1)];
}

/** Generate Mon-start week buckets inside the quarter */
function buildWeekStarts(start: Date, end: Date): Date[] {
  const weeks: Date[] = [];
  // find first Monday on or after start
  const d = new Date(start);
  const dow = d.getDay(); // 0=Sun
  const toMon = dow === 0 ? 1 : dow === 1 ? 0 : 8 - dow;
  d.setDate(d.getDate() + toMon);
  while (d < end) {
    weeks.push(new Date(d));
    d.setDate(d.getDate() + 7);
  }
  return weeks;
}

function weekLabel(d: Date): string {
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

function overlapsWeek(start: Date, end: Date, weekStart: Date): boolean {
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 7);
  return start < weekEnd && end > weekStart;
}

interface Props {
  assignments: AssignmentOut[];
  conflicts: ConflictOut[];
  employees: EmployeeResponse[];
  quarter: string;
  year: number;
}

export default function ClassicMode({ assignments, conflicts, employees, quarter, year }: Props) {
  const ganttRef = useRef<HTMLDivElement>(null);
  const [conflictVisible, setConflictVisible] = useState(false);
  const [scale, setScale] = useState('week');
  const resourceContainerRef = useRef<HTMLDivElement>(null);
  const splitterRef = useRef<HTMLDivElement>(null);

  const [qStart, qEnd] = useMemo(() => quarterBounds(quarter, year), [quarter, year]);

  // Filter assignments to only those with valid dates
  const validAssignments = useMemo(
    () => assignments.filter(a => a.start_date && a.end_date),
    [assignments]
  );

  const weekStarts = useMemo(() => buildWeekStarts(qStart, qEnd), [qStart, qEnd]);

  const activeConflicts = useMemo(
    () => conflicts.filter(c => c.status !== 'resolved'),
    [conflicts]
  );

  // Build gantt task data from assignments
  const ganttData = useMemo(() => {
    if (validAssignments.length === 0) return { data: [], links: [] };

    // Group by backlog_item_id
    const itemMap = new Map<string, AssignmentOut[]>();
    for (const a of validAssignments) {
      if (!itemMap.has(a.backlog_item_id)) itemMap.set(a.backlog_item_id, []);
      itemMap.get(a.backlog_item_id)!.push(a);
    }

    const data: any[] = [];
    let idCounter = 1;
    const itemIdMap = new Map<string, number>(); // backlog_item_id → gantt parent id

    for (const [itemId, phases] of itemMap) {
      const parentId = idCounter++;
      itemIdMap.set(itemId, parentId);
      const minStart = phases.reduce((m, a) => (a.start_date! < m ? a.start_date! : m), phases[0].start_date!);
      const maxEnd = phases.reduce((m, a) => (a.end_date! > m ? a.end_date! : m), phases[0].end_date!);
      const startD = new Date(minStart);
      const endD = new Date(maxEnd);
      const duration = Math.max(1, Math.round((endD.getTime() - startD.getTime()) / 86400000));
      const first = phases[0];
      data.push({
        id: parentId,
        text: first.backlog_item_key ?? first.backlog_item_title?.slice(0, 30) ?? itemId,
        start_date: minStart,
        duration,
        type: 'project',
        open: true,
        progress: 0,
        color: COLORS.summary,
      });
    }

    // Conflict sets for quick lookup
    const conflictItemIds = new Set(activeConflicts.filter(c => c.backlog_item_id).map(c => c.backlog_item_id!));
    const conflictEmpIds = new Set(activeConflicts.filter(c => c.employee_id).map(c => c.employee_id!));

    for (const a of validAssignments) {
      const parentId = itemIdMap.get(a.backlog_item_id);
      if (!parentId) continue;
      const phaseId = idCounter++;
      const color = (COLORS as any)[a.phase] ?? COLORS.summary;
      const hasConflict = conflictItemIds.has(a.backlog_item_id) || (a.employee_id ? conflictEmpIds.has(a.employee_id) : false);
      const startD = new Date(a.start_date!);
      const endD = new Date(a.end_date!);
      const duration = Math.max(1, Math.round((endD.getTime() - startD.getTime()) / 86400000));
      data.push({
        id: phaseId,
        text: a.backlog_item_key ?? '?',
        start_date: a.start_date!,
        duration,
        parent: parentId,
        role: a.phase,
        color,
        assignees: a.employee_name ?? '(пул)',
        est_h: a.hours_allocated ?? null,
        conflict: hasConflict,
        progress: 0,
      });
    }

    return { data, links: [] };
  }, [validAssignments, activeConflicts]);

  // Build resource view (SVG heatmap)
  const buildResourceView = useMemo(() => {
    return (containerId: string) => {
      const container = document.getElementById(containerId);
      if (!container) return;
      container.innerHTML = '';

      const RESOURCES = employees.map(e => ({
        id: e.id,
        name: e.display_name,
        role: e.role ?? '',
        color: (COLORS as any)[e.role ?? ''] ?? '#888',
      }));

      if (RESOURCES.length === 0) return;

      const ROW_H = 26;
      const LABEL_W = 180;
      const CELL_W = 44;
      const numWeeks = weekStarts.length;
      if (numWeeks === 0) return;
      const totalW = LABEL_W + CELL_W * numWeeks;
      const headerH = 28;
      const totalH = headerH + RESOURCES.length * ROW_H;

      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('width', '100%');
      svg.setAttribute('height', String(totalH));
      svg.setAttribute('viewBox', `0 0 ${totalW} ${totalH}`);
      svg.setAttribute('preserveAspectRatio', 'xMinYMin meet');
      svg.style.display = 'block';
      svg.style.background = '#1f1f1f';
      svg.style.overflow = 'visible';

      const hdrRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      hdrRect.setAttribute('x', '0'); hdrRect.setAttribute('y', '0');
      hdrRect.setAttribute('width', String(totalW)); hdrRect.setAttribute('height', String(headerH));
      hdrRect.setAttribute('fill', '#262626');
      svg.appendChild(hdrRect);

      const hdrLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      hdrLabel.setAttribute('x', '8'); hdrLabel.setAttribute('y', String(headerH / 2 + 4));
      hdrLabel.setAttribute('fill', '#8c8c8c'); hdrLabel.setAttribute('font-size', '10');
      hdrLabel.setAttribute('font-family', 'Segoe UI, system-ui');
      hdrLabel.textContent = 'СОТРУДНИК';
      svg.appendChild(hdrLabel);

      weekStarts.forEach((ws, wi) => {
        const x = LABEL_W + wi * CELL_W + CELL_W / 2;
        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('x', String(x)); t.setAttribute('y', String(headerH / 2 + 4));
        t.setAttribute('text-anchor', 'middle'); t.setAttribute('fill', '#8c8c8c');
        t.setAttribute('font-size', '9'); t.setAttribute('font-family', 'Segoe UI, system-ui');
        t.textContent = weekLabel(ws);
        svg.appendChild(t);
      });

      const hdrLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      hdrLine.setAttribute('x1', '0'); hdrLine.setAttribute('y1', String(headerH));
      hdrLine.setAttribute('x2', String(totalW)); hdrLine.setAttribute('y2', String(headerH));
      hdrLine.setAttribute('stroke', '#303030'); hdrLine.setAttribute('stroke-width', '1');
      svg.appendChild(hdrLine);

      // Compute weekly load per employee
      RESOURCES.forEach((res, ri) => {
        const empAssignments = validAssignments.filter(a => a.employee_id === res.id);
        const loads = weekStarts.map(ws => {
          const weekEnd = new Date(ws);
          weekEnd.setDate(weekEnd.getDate() + 5); // Mon–Fri
          let totalH = 0;
          for (const a of empAssignments) {
            if (!a.start_date || !a.end_date || !a.hours_allocated) continue;
            const aStart = new Date(a.start_date);
            const aEnd = new Date(a.end_date);
            if (!overlapsWeek(aStart, aEnd, ws)) continue;
            // Pro-rate hours over the assignment duration (in days)
            const totalDays = Math.max(1, Math.round((aEnd.getTime() - aStart.getTime()) / 86400000));
            const overlapStart = aStart > ws ? aStart : ws;
            const overlapEnd = aEnd < weekEnd ? aEnd : weekEnd;
            const overlapDays = Math.max(0, Math.round((overlapEnd.getTime() - overlapStart.getTime()) / 86400000));
            totalH += (a.hours_allocated * overlapDays) / totalDays;
          }
          const capacity = 5 * 8; // 40h per week
          return Math.round((totalH / capacity) * 100);
        });

        const rowY = headerH + ri * ROW_H;
        const isEven = ri % 2 === 0;

        const rowBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rowBg.setAttribute('x', '0'); rowBg.setAttribute('y', String(rowY));
        rowBg.setAttribute('width', String(totalW)); rowBg.setAttribute('height', String(ROW_H));
        rowBg.setAttribute('fill', isEven ? '#1f1f1f' : '#222222');
        svg.appendChild(rowBg);

        const roleRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        roleRect.setAttribute('x', '0'); roleRect.setAttribute('y', String(rowY + 6));
        roleRect.setAttribute('width', '3'); roleRect.setAttribute('height', String(ROW_H - 12));
        roleRect.setAttribute('fill', res.color); roleRect.setAttribute('rx', '1');
        svg.appendChild(roleRect);

        const nameText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        nameText.setAttribute('x', '10'); nameText.setAttribute('y', String(rowY + ROW_H / 2 + 4));
        nameText.setAttribute('fill', '#e6e6e6'); nameText.setAttribute('font-size', '11');
        nameText.setAttribute('font-family', 'Segoe UI, system-ui');
        nameText.textContent = res.name;
        svg.appendChild(nameText);

        const vLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        vLine.setAttribute('x1', String(LABEL_W)); vLine.setAttribute('y1', String(rowY));
        vLine.setAttribute('x2', String(LABEL_W)); vLine.setAttribute('y2', String(rowY + ROW_H));
        vLine.setAttribute('stroke', '#303030'); vLine.setAttribute('stroke-width', '1');
        svg.appendChild(vLine);

        loads.forEach((load, wi) => {
          const cellX = LABEL_W + wi * CELL_W;
          let barColor: string, textColor: string;
          if (load > 110) { barColor = 'rgba(255,77,79,0.25)'; textColor = '#ff4d4f'; }
          else if (load > 85) { barColor = 'rgba(250,173,20,0.18)'; textColor = '#faad14'; }
          else if (load > 0) { barColor = 'rgba(82,196,26,0.15)'; textColor = '#52c41a'; }
          else { barColor = 'transparent'; textColor = '#444'; }

          const cellRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          cellRect.setAttribute('x', String(cellX + 2)); cellRect.setAttribute('y', String(rowY + 3));
          cellRect.setAttribute('width', String(CELL_W - 4)); cellRect.setAttribute('height', String(ROW_H - 6));
          cellRect.setAttribute('fill', barColor); cellRect.setAttribute('rx', '3');
          svg.appendChild(cellRect);

          if (load > 0) {
            const barH = Math.min(load / 150, 1) * (ROW_H - 10);
            const barRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            barRect.setAttribute('x', String(cellX + 4)); barRect.setAttribute('y', String(rowY + ROW_H - 4 - barH));
            barRect.setAttribute('width', String(CELL_W - 8)); barRect.setAttribute('height', String(barH));
            barRect.setAttribute('fill', load > 110 ? 'rgba(255,77,79,0.5)' : load > 85 ? 'rgba(250,173,20,0.4)' : 'rgba(82,196,26,0.4)');
            barRect.setAttribute('rx', '2');
            svg.appendChild(barRect);
          }

          const loadText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          loadText.setAttribute('x', String(cellX + CELL_W / 2)); loadText.setAttribute('y', String(rowY + ROW_H / 2 + 4));
          loadText.setAttribute('text-anchor', 'middle'); loadText.setAttribute('fill', textColor);
          loadText.setAttribute('font-size', '10'); loadText.setAttribute('font-weight', load > 100 ? 'bold' : 'normal');
          loadText.setAttribute('font-family', 'Segoe UI, system-ui');
          loadText.textContent = load > 0 ? `${load}%` : '';
          svg.appendChild(loadText);

          if (load > 110) {
            const wt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            wt.setAttribute('x', String(cellX + CELL_W - 4)); wt.setAttribute('y', String(rowY + 12));
            wt.setAttribute('text-anchor', 'end'); wt.setAttribute('fill', '#ff4d4f'); wt.setAttribute('font-size', '8');
            wt.textContent = '!';
            svg.appendChild(wt);
          }

          const cellBorder = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          cellBorder.setAttribute('x1', String(cellX + CELL_W)); cellBorder.setAttribute('y1', String(rowY));
          cellBorder.setAttribute('x2', String(cellX + CELL_W)); cellBorder.setAttribute('y2', String(rowY + ROW_H));
          cellBorder.setAttribute('stroke', '#2a2a2a'); cellBorder.setAttribute('stroke-width', '1');
          svg.appendChild(cellBorder);
        });

        const rowLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        rowLine.setAttribute('x1', '0'); rowLine.setAttribute('y1', String(rowY + ROW_H));
        rowLine.setAttribute('x2', String(totalW)); rowLine.setAttribute('y2', String(rowY + ROW_H));
        rowLine.setAttribute('stroke', '#282828'); rowLine.setAttribute('stroke-width', '1');
        svg.appendChild(rowLine);
      });

      const wrap = document.createElement('div');
      wrap.style.overflowX = 'auto';
      wrap.style.overflowY = 'auto';
      wrap.style.height = '100%';
      wrap.style.background = '#1f1f1f';
      wrap.appendChild(svg);
      container.appendChild(wrap);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [validAssignments, employees, weekStarts]);

  useEffect(() => {
    if (!ganttRef.current) return;

    gantt.clearAll();

    try { gantt.plugins({ marker: true, tooltip: true } as any); } catch { /* already loaded */ }
    try { (gantt as any).i18n.setLocale('ru'); } catch { /* skip */ }

    gantt.config.show_progress = true;
    (gantt.config as any).drag_progress = true;
    gantt.config.drag_resize = true;
    gantt.config.drag_move = true;
    gantt.config.drag_links = true;
    (gantt.config as any).auto_types = true;
    gantt.config.date_format = '%Y-%m-%d';
    gantt.config.start_date = qStart;
    gantt.config.end_date = qEnd;
    gantt.config.row_height = 30;
    gantt.config.bar_height = 18;
    gantt.config.scale_height = 46;
    (gantt.config as any).min_column_width = 32;
    gantt.config.fit_tasks = false;
    gantt.config.show_unscheduled = true;
    (gantt.config as any).round_dnd_dates = true;
    gantt.config.open_tree_initially = false;

    gantt.config.columns = [
      { name: 'text', label: 'Инициатива / Фаза', width: 200, tree: true, resize: true },
      {
        name: 'role', label: 'Роль', width: 80, resize: true, align: 'center',
        template: (task: any) => {
          const labels: Record<string, string> = { analyst: 'Анализ', dev: 'Разработка', qa: 'QA', opo: 'ОПЭ' };
          if (task.type === 'project') return '';
          const l = labels[task.role] || '';
          const c = (COLORS as any)[task.role] || '#888';
          return `<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:${c}22;color:${c};border:1px solid ${c}44">${l}</span>`;
        }
      },
      {
        name: 'assignees', label: 'Исполнители', width: 150, resize: true,
        template: (task: any) => {
          if (task.type === 'project') return '';
          return `<span style="color:#8c8c8c;font-size:11px">${task.assignees || '—'}</span>`;
        }
      },
      {
        name: 'est_h', label: 'Оценка ч.', width: 64, align: 'right', resize: true,
        template: (task: any) => {
          if (task.type === 'project') return '';
          const conflict = task.conflict ? '<span style="color:#ff4d4f;margin-left:3px" title="Перегрузка">⚠</span>' : '';
          return `<span style="color:#8c8c8c">${task.est_h ?? '—'}</span>${conflict}`;
        }
      },
    ] as any;

    gantt.config.scales = [
      { unit: 'month', step: 1, format: '%F %Y' },
      {
        unit: 'week', step: 1, format: (date: Date) => {
          const d = new Date(date);
          const end = new Date(d.getTime() + 6 * 24 * 60 * 60 * 1000);
          return `${d.getDate()}/${d.getMonth() + 1}–${end.getDate()}/${end.getMonth() + 1}`;
        }
      }
    ] as any;

    gantt.templates.task_class = (_start: any, _end: any, task: any) => {
      const cls: string[] = [];
      if (task.conflict) cls.push('conflict-task');
      if (task.type === 'project') cls.push('gantt_project');
      return cls.join(' ');
    };

    gantt.templates.tooltip_text = (_start: any, _end: any, task: any) => {
      if (task.type === 'project') return `<b>${task.text}</b>`;
      const roleLabels: Record<string, string> = { analyst: 'Анализ', dev: 'Разработка', qa: 'Тестирование', opo: 'ОПЭ' };
      const pct = Math.round((task.progress || 0) * 100);
      const conflictWarn = task.conflict ? '<div style="color:#ff4d4f;margin-top:6px">⚠ Обнаружен конфликт перегрузки</div>' : '';
      return `<b>${task.text}</b>` +
        `<div style="margin-top:6px;color:#8c8c8c">Роль: ${roleLabels[task.role] || task.role || '—'}</div>` +
        `<div style="color:#8c8c8c">Исполнители: ${task.assignees || '—'}</div>` +
        `<div style="color:#8c8c8c">Оценка: ${task.est_h ?? '—'} ч.</div>` +
        `<div style="color:#8c8c8c">Готовность: ${pct}%</div>` +
        conflictWarn;
    };

    gantt.templates.scale_cell_class = (date: Date) => {
      return (date.getDay() === 0 || date.getDay() === 6) ? 'week_end' : '';
    };
    gantt.templates.timeline_cell_class = (_task: any, date: Date) => {
      return (date.getDay() === 0 || date.getDay() === 6) ? 'week_end' : '';
    };

    gantt.attachEvent('onTaskLoading', (task: any) => {
      task.color = task.color || COLORS.summary;
      return true;
    });

    gantt.init(ganttRef.current);

    if (ganttData.data.length > 0) {
      gantt.parse(ganttData);
    }

    if ((gantt as any).addMarker) {
      (gantt as any).addMarker({ start_date: new Date(), css: 'today_line', text: 'Сегодня', title: 'Сегодня' });
    }

    buildResourceView('resource-gantt-container-classic');

    return () => {
      try { gantt.clearAll(); } catch { /* ignore */ }
    };
  }, [ganttData, qStart, qEnd, buildResourceView]);

  // Splitter drag
  useEffect(() => {
    const splitter = splitterRef.current;
    const ganttDiv = ganttRef.current;
    const resDiv = resourceContainerRef.current;
    if (!splitter || !ganttDiv || !resDiv) return;

    let dragging = false;
    let startY = 0, startGanttH = 0, startResH = 0;

    const onMouseDown = (e: MouseEvent) => {
      dragging = true;
      startY = e.clientY;
      startGanttH = ganttDiv.offsetHeight;
      startResH = resDiv.offsetHeight;
      splitter.classList.add('dragging');
      document.body.style.cursor = 'ns-resize';
      e.preventDefault();
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging) return;
      const dy = e.clientY - startY;
      const newGantt = Math.max(120, startGanttH + dy);
      const newRes = Math.max(100, startResH - dy);
      ganttDiv.style.height = `${newGantt}px`;
      ganttDiv.style.flex = 'none';
      resDiv.style.height = `${newRes}px`;
      gantt.render();
    };
    const onMouseUp = () => {
      if (!dragging) return;
      dragging = false;
      splitter.classList.remove('dragging');
      document.body.style.cursor = '';
      gantt.render();
    };

    splitter.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      splitter.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  const applyScale = (v: string) => {
    setScale(v);
    if (v === 'week') {
      gantt.config.scales = [
        { unit: 'month', step: 1, format: '%F %Y' },
        {
          unit: 'week', step: 1, format: (date: Date) => {
            const d = new Date(date);
            const end = new Date(d.getTime() + 6 * 24 * 60 * 60 * 1000);
            return `${d.getDate()}/${d.getMonth() + 1}–${end.getDate()}/${end.getMonth() + 1}`;
          }
        }
      ] as any;
      (gantt.config as any).min_column_width = 32;
    } else if (v === 'month') {
      gantt.config.scales = [
        { unit: 'year', step: 1, format: '%Y' },
        { unit: 'month', step: 1, format: '%M' }
      ] as any;
      (gantt.config as any).min_column_width = 80;
    } else {
      gantt.config.scales = [
        { unit: 'week', step: 1, format: 'Неделя %W' },
        { unit: 'day', step: 1, format: '%d' }
      ] as any;
      (gantt.config as any).min_column_width = 28;
    }
    gantt.render();
  };

  const uniqueItems = new Set(validAssignments.map(a => a.backlog_item_id)).size;
  const dateStr = `${qStart.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })} – ${new Date(qEnd.getTime() - 86400000).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}`;

  if (validAssignments.length === 0) {
    return (
      <div className="dhtmlx-classic-mode">
        <Empty description="Нет данных для отображения" style={{ paddingTop: 80, color: '#8c8c8c' }} />
      </div>
    );
  }

  return (
    <div className="dhtmlx-classic-mode">
      {/* Page Header */}
      <header className="page-header">
        <div className="header-title">
          Планирование ресурсов
          <span>· DHTMLX Classic</span>
        </div>
        <div className="header-divider" />
        <div className="header-controls">
          <span className="ctrl-label">Просмотр</span>
          <select className="ctrl-select" value={scale} onChange={e => applyScale(e.target.value)}>
            <option value="week">По неделям</option>
            <option value="month">По месяцам</option>
            <option value="day">По дням</option>
          </select>
        </div>
        <div className="header-spacer" />
        <div className="legend">
          <div className="legend-item"><div className="legend-dot" style={{ background: '#5b8dee' }}></div>Анализ</div>
          <div className="legend-item"><div className="legend-dot" style={{ background: '#36cfc9' }}></div>Разработка</div>
          <div className="legend-item"><div className="legend-dot" style={{ background: '#9254de' }}></div>Тестирование</div>
          <div className="legend-item"><div className="legend-dot" style={{ background: '#fa8c16' }}></div>ОПЭ</div>
        </div>
        <div className="header-divider" />
        <div className="conflict-badge" onClick={() => setConflictVisible(v => !v)}>
          ⚠ {activeConflicts.length} конфликтов
        </div>
      </header>

      {/* Main Gantt Area */}
      <div className="gantt-wrapper">
        <div id="gantt-container-classic" ref={ganttRef}></div>
        <div className="splitter" ref={splitterRef}></div>
        <div id="resource-container-classic" ref={resourceContainerRef}>
          <div className="resource-header">
            Загрузка сотрудников
            <span className="rh-tag">Resource View</span>
          </div>
          <div id="resource-gantt-container-classic"></div>
        </div>
      </div>

      {/* Status Bar */}
      <div className="status-bar">
        <span><span className="status-dot"></span>{quarter} {year} · {dateStr}</span>
        <span>·</span>
        <span>{uniqueItems} инициатив · {validAssignments.length} фаз</span>
        <span>·</span>
        <span>{employees.length} сотрудников</span>
        <span>·</span>
        <span style={{ color: '#ff4d4f' }}>{activeConflicts.length} конфликтов</span>
        <div style={{ flex: 1 }}></div>
        <span>DHTMLX Gantt Standard (GPL-2.0)</span>
      </div>

      {/* Conflict Panel */}
      <div className={`conflict-panel${conflictVisible ? ' visible' : ''}`}>
        <div className="conflict-panel-header">
          <div className="conflict-panel-title">⚠ Конфликты ({activeConflicts.length})</div>
          <div className="conflict-panel-close" onClick={() => setConflictVisible(false)}>×</div>
        </div>
        <div className="conflict-list">
          {activeConflicts.map(c => (
            <div key={c.id} className="conflict-item">
              <div className="conflict-item-person">{c.backlog_item_title ?? '—'} · {c.severity}</div>
              {(c.window_start || c.window_end) && (
                <div className="conflict-item-dates">{c.window_start ?? ''} – {c.window_end ?? ''}</div>
              )}
              <div className="conflict-item-load">{c.message}</div>
            </div>
          ))}
          {activeConflicts.length === 0 && (
            <div style={{ color: '#8c8c8c', padding: '16px', textAlign: 'center' }}>Конфликтов нет</div>
          )}
        </div>
      </div>
    </div>
  );
}
