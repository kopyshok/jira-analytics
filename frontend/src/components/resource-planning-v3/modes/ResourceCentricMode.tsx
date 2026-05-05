import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Empty } from 'antd';
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import './resource-centric.css';
import type { AssignmentOut, ConflictOut } from '../../../api/resourcePlanning';
import type { EmployeeResponse } from '../../../types/api';

const PHASE_LABELS: Record<string, string> = { analyst: 'Анализ', dev: 'Разработка', qa: 'Тестирование', opo: 'ОПЭ' };
const PHASE_LETTERS: Record<string, string> = { analyst: 'А', dev: 'Р', qa: 'Т', opo: 'О' };
const PHASE_COLORS: Record<string, { bar: string; text: string }> = {
  analyst: { bar: '#2563d4', text: '#a8c8ff' },
  dev:     { bar: '#6d28d9', text: '#c4b5fd' },
  qa:      { bar: '#16a34a', text: '#86efac' },
  opo:     { bar: '#b45309', text: '#fcd34d' },
};
const ROLE_META: Record<string, { name: string; color: string; icon: string }> = {
  analyst: { name: 'Аналитики',    color: '#69b1ff', icon: '🔍' },
  dev:     { name: 'Разработчики', color: '#b37feb', icon: '💻' },
  qa:      { name: 'Тестировщики', color: '#95de64', icon: '🧪' },
  opo:     { name: 'ОПЭ',          color: '#ffa940', icon: '🚀' },
};

/** Infer role bucket from Employee.role string */
function inferRoleBucket(role: string | null): string {
  if (!role) return 'dev';
  const r = role.toLowerCase();
  if (r.includes('analyst') || r.includes('аналитик')) return 'analyst';
  if (r.includes('qa') || r.includes('тест') || r.includes('test')) return 'qa';
  if (r.includes('ope') || r.includes('опэ')) return 'opo';
  return 'dev';
}

function quarterBounds(quarter: string, year: number): [Date, Date] {
  const q = parseInt(quarter.replace('Q', ''), 10) || 3;
  const startMonth = (q - 1) * 3;
  return [new Date(year, startMonth, 1), new Date(year, startMonth + 3, 1)];
}

interface Props {
  assignments: AssignmentOut[];
  conflicts: ConflictOut[];
  employees: EmployeeResponse[];
  quarter: string;
  year: number;
}

export default function ResourceCentricMode({ assignments, conflicts, employees, quarter, year }: Props) {
  const ganttRef = useRef<HTMLDivElement>(null);
  const toastContainerRef = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarTitle, setSidebarTitle] = useState('Детали инициативы');
  const [sidebarContent, setSidebarContent] = useState<string>('');
  const [scaleActive, setScaleActive] = useState<'week' | 'day' | 'month'>('week');
  const [roleFilter, setRoleFilter] = useState('');
  const [initFilter, setInitFilter] = useState('');

  const [qStart, qEnd] = useMemo(() => quarterBounds(quarter, year), [quarter, year]);

  const validAssignments = useMemo(
    () => assignments.filter(a => a.start_date && a.end_date),
    [assignments]
  );

  const activeConflicts = useMemo(
    () => conflicts.filter(c => c.status !== 'resolved'),
    [conflicts]
  );

  // Build employee map
  const empMap = useMemo(() => {
    const m = new Map<string, EmployeeResponse>();
    employees.forEach(e => m.set(e.id, e));
    return m;
  }, [employees]);

  // Unique initiatives from assignments
  const initiatives = useMemo(() => {
    const m = new Map<string, { id: string; key: string | null; name: string }>();
    for (const a of validAssignments) {
      if (!m.has(a.backlog_item_id)) {
        m.set(a.backlog_item_id, {
          id: a.backlog_item_id,
          key: a.backlog_item_key,
          name: a.backlog_item_title,
        });
      }
    }
    return Array.from(m.values());
  }, [validAssignments]);

  const showToast = useCallback((icon: string, msg: string) => {
    const container = toastContainerRef.current;
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
    container.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }, []);

  const showConflictPanel = useCallback(() => {
    let html = `<div style="font-size:13px;font-weight:600;color:#ff4d4f;margin-bottom:14px;">⚠ Конфликты (${activeConflicts.length})</div>`;
    if (activeConflicts.length === 0) {
      html += `<div style="color:#595959;text-align:center;padding:16px;">Конфликтов нет</div>`;
    }
    activeConflicts.forEach(c => {
      html += `<div style="padding:10px 12px;background:rgba(255,77,79,0.08);border:1px solid rgba(255,77,79,0.25);border-radius:6px;margin-bottom:8px;">
        <div style="font-weight:600;color:#e6e6e6;margin-bottom:4px;">${c.backlog_item_title ?? '—'} · ${c.severity}</div>
        <div style="font-size:11px;color:#8c8c8c;">${c.window_start ?? ''} – ${c.window_end ?? ''}</div>
        <div style="font-size:11px;color:#ff4d4f;margin-top:4px;">${c.message}</div>
      </div>`;
    });
    setSidebarTitle('Конфликты');
    setSidebarContent(html);
    setSidebarOpen(true);
  }, [activeConflicts]);

  const showTaskDetail = useCallback((task: any) => {
    const itemId: string = task._itemId;
    const phase: string = task._phase;

    const itemAssignments = validAssignments.filter(a => a.backlog_item_id === itemId);
    const initName = itemAssignments[0]?.backlog_item_title ?? task.text;
    const initKey = itemAssignments[0]?.backlog_item_key ?? '';

    const phases: string[] = ['analyst', 'dev', 'qa', 'opo'];
    const phaseItems = phases.map(ph => {
      const phaseTasks = itemAssignments.filter(a => a.phase === ph);
      if (!phaseTasks.length) return '';
      const minStart = phaseTasks.reduce((m, a) => (a.start_date! < m ? a.start_date! : m), phaseTasks[0].start_date!);
      const maxEnd = phaseTasks.reduce((m, a) => (a.end_date! > m ? a.end_date! : m), phaseTasks[0].end_date!);
      const hasConflict = activeConflicts.some(c => c.backlog_item_id === itemId);
      const now = new Date();
      const startD = new Date(minStart), endD = new Date(maxEnd);
      let status = 'pending', statusLabel = 'Ожидание';
      if (endD < now) { status = 'done'; statusLabel = 'Готово'; }
      else if (startD <= now) { status = 'active'; statusLabel = 'В работе'; }
      if (hasConflict) { status = 'conflict'; statusLabel = 'Конфликт'; }
      const phColor = PHASE_COLORS[ph]?.bar ?? '#888';
      const letter = PHASE_LETTERS[ph] ?? ph[0].toUpperCase();
      return `<div class="phase-item">
        <div class="phase-icon" style="background:${phColor}22;color:${phColor};border:1px solid ${phColor}44;">${letter}</div>
        <div class="phase-info">
          <div class="phase-name">${PHASE_LABELS[ph] ?? ph}</div>
          <div class="phase-dates">${minStart.slice(5)} — ${maxEnd.slice(5)}</div>
        </div>
        <div class="phase-status ${status}">${statusLabel}</div>
      </div>`;
    }).join('');

    const assigneeIds = [...new Set(itemAssignments.map(a => a.employee_id).filter(Boolean) as string[])];
    const chipHtml = assigneeIds.map(eid => {
      const e = empMap.get(eid);
      if (!e) {
        const a = itemAssignments.find(x => x.employee_id === eid);
        const name = a?.employee_name ?? eid;
        const initials = name.split(' ').map((p: string) => p[0]).join('').slice(0, 2);
        return `<div class="assignee-chip"><div class="chip-avatar" style="background:#555">${initials}</div><span>${name}</span></div>`;
      }
      const roleBucket = inferRoleBucket(e.role);
      const color = ROLE_META[roleBucket]?.color ?? '#888';
      const initials = e.display_name.split(' ').map((p: string) => p[0]).join('').slice(0, 2);
      return `<div class="assignee-chip"><div class="chip-avatar" style="background:${color}cc">${initials}</div><span>${e.display_name}</span></div>`;
    }).join('');

    const conflictCount = activeConflicts.filter(c => c.backlog_item_id === itemId).length;
    const phaseLabel = PHASE_LABELS[phase] ?? phase;

    setSidebarTitle(initName);
    setSidebarContent(`
      <div class="detail-name">${initName}</div>
      <div class="detail-key">${initKey}</div>
      <div class="detail-section">
        <div class="detail-section-title">Параметры</div>
        <div class="detail-row"><span class="detail-label">Квартал</span><span class="detail-value">${quarter} ${year}</span></div>
        <div class="detail-row"><span class="detail-label">Выбранная фаза</span><span class="detail-value">${phaseLabel}</span></div>
        ${conflictCount > 0 ? `<div class="detail-row"><span class="detail-label" style="color:var(--danger);">⚠ Конфликты</span><span class="detail-value" style="color:var(--danger);">${conflictCount}</span></div>` : ''}
      </div>
      <div class="detail-section">
        <div class="detail-section-title">Фазы инициативы</div>
        <div class="phase-list">${phaseItems}</div>
      </div>
      <div class="detail-section">
        <div class="detail-section-title">Назначены (${assigneeIds.length})</div>
        <div class="assignee-chips">${chipHtml}</div>
      </div>
    `);
    setSidebarOpen(true);
  }, [validAssignments, empMap, activeConflicts, quarter, year]);

  // Build gantt data
  const ganttData = useMemo(() => {
    const tasks: any[] = [];
    let order = 1;

    // Group employees by role bucket
    const empsByRole = new Map<string, EmployeeResponse[]>();
    for (const e of employees) {
      const bucket = inferRoleBucket(e.role);
      if (!empsByRole.has(bucket)) empsByRole.set(bucket, []);
      empsByRole.get(bucket)!.push(e);
    }

    // Also handle pool assignments (no employee_id)
    const roleOrder = ['analyst', 'dev', 'qa', 'opo'];
    for (const roleId of roleOrder) {
      const roleMeta = ROLE_META[roleId];
      const groupId = 'g_' + roleId;
      tasks.push({
        id: groupId,
        text: roleMeta.name,
        type: 'project',
        open: true,
        render: 'split',
        color: 'transparent',
        _isGroup: true,
        _role: roleId,
        _roleColor: roleMeta.color,
        order: order++,
      });

      const roleEmps = empsByRole.get(roleId) ?? [];
      for (const emp of roleEmps) {
        tasks.push({
          id: emp.id,
          text: emp.display_name,
          type: 'project',
          parent: groupId,
          open: true,
          render: 'split',
          color: 'transparent',
          _isEmployee: true,
          _emp: emp,
          _role: roleId,
          _roleColor: roleMeta.color,
          order: order++,
        });

        const empAssignments = validAssignments.filter(a => a.employee_id === emp.id && a.phase === roleId);
        for (const a of empAssignments) {
          const phaseMeta = PHASE_COLORS[a.phase];
          const hasConflict = activeConflicts.some(
            c => (c.backlog_item_id === a.backlog_item_id) || (c.employee_id === emp.id)
          );
          tasks.push({
            id: a.id,
            text: (PHASE_LETTERS[a.phase] ?? a.phase) + ' · ' + (a.backlog_item_key ?? a.backlog_item_title),
            start_date: a.start_date!,
            end_date: a.end_date!,
            parent: emp.id,
            color: phaseMeta?.bar ?? '#888',
            _conflict: hasConflict,
            _itemId: a.backlog_item_id,
            _phase: a.phase,
            _emp: emp,
            order: order++,
            progress: 0,
          });
        }
      }

      // Pool assignments for this role
      const poolAssignments = validAssignments.filter(a => !a.employee_id && a.phase === roleId);
      if (poolAssignments.length > 0) {
        const poolId = 'pool_' + roleId;
        tasks.push({
          id: poolId,
          text: '(пул)',
          type: 'project',
          parent: groupId,
          open: true,
          render: 'split',
          color: 'transparent',
          _isEmployee: true,
          _emp: { id: poolId, display_name: '(пул)', role: roleId },
          _role: roleId,
          _roleColor: roleMeta.color,
          order: order++,
        });
        for (const a of poolAssignments) {
          tasks.push({
            id: a.id,
            text: (PHASE_LETTERS[a.phase] ?? a.phase) + ' · ' + (a.backlog_item_key ?? a.backlog_item_title),
            start_date: a.start_date!,
            end_date: a.end_date!,
            parent: poolId,
            color: PHASE_COLORS[a.phase]?.bar ?? '#888',
            _conflict: false,
            _itemId: a.backlog_item_id,
            _phase: a.phase,
            order: order++,
            progress: 0,
          });
        }
      }
    }

    return { data: tasks, links: [] };
  }, [validAssignments, employees, activeConflicts]);

  useEffect(() => {
    if (!ganttRef.current) return;

    gantt.clearAll();

    try { (gantt as any).i18n.setLocale('ru'); } catch { /* skip */ }

    gantt.config.layout = {
      css: 'gantt_container',
      rows: [
        {
          cols: [
            { view: 'grid', width: 230, scrollY: 'scrollVer' },
            { resizer: true, width: 1 },
            { view: 'timeline', scrollX: 'scrollHor', scrollY: 'scrollVer' },
            { view: 'scrollbar', id: 'scrollVer' },
          ]
        },
        { view: 'scrollbar', id: 'scrollHor' },
      ]
    } as any;

    gantt.config.row_height = 40;
    gantt.config.bar_height = 26;
    (gantt.config as any).min_column_width = 40;
    gantt.config.fit_tasks = false;
    (gantt.config as any).autofit = false;
    gantt.config.auto_scheduling = false;
    gantt.config.drag_links = false;
    (gantt.config as any).order_branch = true;
    gantt.config.open_tree_initially = true;
    gantt.config.show_progress = true;
    (gantt.config as any).round_dnd_dates = true;
    (gantt.config as any).drag_progress = false;
    (gantt.config as any).multiselect = false;
    gantt.config.date_format = '%Y-%m-%d';

    gantt.config.scales = [
      { unit: 'month', step: 1, format: '%F %Y' },
      { unit: 'week', step: 1, format: 'Нед %W' },
    ] as any;

    gantt.config.start_date = qStart;
    gantt.config.end_date = qEnd;

    gantt.config.columns = [
      {
        name: 'text',
        label: 'Сотрудник / Роль',
        width: 210,
        tree: true,
        template: (task: any) => {
          if (task._isGroup) {
            const role = ROLE_META[task._role];
            return `<div class="group-cell"><div class="role-dot" style="background:${role?.color}"></div><span>${role?.icon} ${role?.name}</span></div>`;
          }
          if (task._isEmployee) {
            const emp = task._emp as EmployeeResponse | { id: string; display_name: string; role: string | null };
            const roleBucket = inferRoleBucket((emp as EmployeeResponse).role ?? null);
            const color = ROLE_META[roleBucket]?.color ?? '#888';
            const name = (emp as EmployeeResponse).display_name ?? (emp as any).name ?? '?';
            const initials = name.split(' ').map((p: string) => p[0]).join('').slice(0, 2);
            return `<div class="employee-cell"><div class="emp-avatar" style="background:${color}cc">${initials}</div><div class="emp-info"><div class="emp-name">${name}</div><div class="emp-role">${ROLE_META[roleBucket]?.name ?? ''}</div></div></div>`;
          }
          return '';
        }
      }
    ] as any;

    gantt.templates.task_class = (_start: any, _end: any, task: any) => {
      if (task._isGroup || task._isEmployee) return 'gantt_project';
      return task._conflict ? ' conflict-bar' : '';
    };

    gantt.templates.task_text = (_start: any, _end: any, task: any) => {
      if (task._isGroup || task._isEmployee) return '';
      return task.text;
    };

    gantt.templates.tooltip_text = (_start: any, _end: any, task: any) => {
      if (task._isGroup || task._isEmployee) return '';
      const phase = task._phase ?? '';
      let html = `<div style="min-width:200px;">
        <div style="font-weight:700;color:#e6e6e6;margin-bottom:6px;">${task.text}</div>
        <div style="color:#8c8c8c;font-size:11px;margin-bottom:4px;">Фаза: <span style="color:#e6e6e6;">${PHASE_LABELS[phase] ?? phase}</span></div>`;
      if (task._conflict) {
        html += `<div style="color:#ff4d4f;font-weight:600;margin-top:8px;padding:6px 8px;background:rgba(255,77,79,0.1);border-radius:4px;border:1px solid rgba(255,77,79,0.3);">⚠ Конфликт перегрузки</div>`;
      }
      html += '</div>';
      return html;
    };

    gantt.templates.task_row_class = (_start: any, _end: any, task: any) => {
      if (!task._isEmployee) return '';
      const empId = task.id as string;
      const hasConflict = activeConflicts.some(c => c.employee_id === empId);
      return hasConflict ? 'overloaded' : '';
    };

    gantt.templates.timeline_cell_class = (_task: any, date: Date) => {
      const d = date.getDay();
      return (d === 0 || d === 6) ? 'week_end' : '';
    };

    gantt.attachEvent('onBeforeTaskDrag', (id: any) => {
      const task = gantt.getTask(id);
      if (task._isGroup || task._isEmployee) return false;
      return true;
    });

    gantt.attachEvent('onAfterTaskDrag', (id: any, mode: any) => {
      const task = gantt.getTask(id);
      if (!task || task._isGroup || task._isEmployee) return;
      if (mode === 'move') showToast('✅', `Перемещено · ${task.text}`);
    });

    gantt.attachEvent('onTaskClick', (id: any) => {
      const task = gantt.getTask(id);
      if (task._isGroup || task._isEmployee) return true;
      showTaskDetail(task);
      return true;
    });

    gantt.attachEvent('onBeforeLightbox', () => false);

    gantt.init(ganttRef.current);
    if (ganttData.data.length > 0) {
      gantt.parse(ganttData);
    }

    return () => {
      try { gantt.clearAll(); } catch { /* ignore */ }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ganttData, qStart, qEnd]);

  const setScale = (mode: 'week' | 'day' | 'month') => {
    setScaleActive(mode);
    if (mode === 'week') {
      gantt.config.scales = [{ unit: 'month', step: 1, format: '%F %Y' }, { unit: 'week', step: 1, format: 'Нед %W' }] as any;
      (gantt.config as any).min_column_width = 100;
    } else if (mode === 'day') {
      gantt.config.scales = [{ unit: 'week', step: 1, format: 'Нед %W · %d %M' }, { unit: 'day', step: 1, format: '%d' }] as any;
      (gantt.config as any).min_column_width = 30;
    } else {
      gantt.config.scales = [{ unit: 'quarter', step: 1, format: 'Q%q %Y' }, { unit: 'month', step: 1, format: '%F' }] as any;
      (gantt.config as any).min_column_width = 120;
    }
    gantt.render();
  };

  const applyFilter = (newRole?: string, newInit?: string) => {
    const r = newRole !== undefined ? newRole : roleFilter;
    const initId = newInit !== undefined ? newInit : initFilter;
    (gantt as any).filter_task = (_id: any, task: any) => {
      if (task._isGroup) { if (r && task._role !== r) return false; return true; }
      if (task._isEmployee) { if (r && task._role !== r) return false; return true; }
      if (r && task._phase !== r) return false;
      if (initId && task._itemId !== initId) return false;
      return true;
    };
    gantt.render();
  };

  if (validAssignments.length === 0) {
    return (
      <div className="dhtmlx-resource-mode" style={{ position: 'relative' }}>
        <Empty description="Нет данных для отображения" style={{ paddingTop: 80, color: '#8c8c8c' }} />
      </div>
    );
  }

  return (
    <div className="dhtmlx-resource-mode" style={{ position: 'relative' }}>
      {/* App Header */}
      <header className="app-header">
        <div className="app-header__logo">
          <div className="app-header__icon">📅</div>
          <div>
            <div className="app-header__title">Планирование · Ресурсо-центричный</div>
            <div className="app-header__subtitle">{quarter} {year}</div>
          </div>
        </div>
        <div className="header-divider" />
        <div className="header-controls">
          <div className="scale-toggle">
            <button className={`scale-btn${scaleActive === 'week' ? ' active' : ''}`} onClick={() => setScale('week')}>Нед</button>
            <button className={`scale-btn${scaleActive === 'day' ? ' active' : ''}`} onClick={() => setScale('day')}>День</button>
            <button className={`scale-btn${scaleActive === 'month' ? ' active' : ''}`} onClick={() => setScale('month')}>Мес</button>
          </div>
          <select className="select-control" value={roleFilter} onChange={e => { setRoleFilter(e.target.value); applyFilter(e.target.value, undefined); }}>
            <option value="">Все роли</option>
            <option value="analyst">Аналитики</option>
            <option value="dev">Разработчики</option>
            <option value="qa">Тестировщики</option>
            <option value="opo">ОПЭ</option>
          </select>
          <select className="select-control" value={initFilter} onChange={e => { setInitFilter(e.target.value); applyFilter(undefined, e.target.value); }}>
            <option value="">Все инициативы</option>
            {initiatives.map(i => <option key={i.id} value={i.id}>{i.key ? `${i.key} · ` : ''}{i.name}</option>)}
          </select>
          <button className="btn" onClick={() => (gantt as any).collapseAll()}>⊟ Свернуть</button>
          <button className="btn" onClick={() => (gantt as any).expandAll()}>⊞ Развернуть</button>
        </div>
        <div className="header-spacer" />
        <div className="conflict-badge" onClick={showConflictPanel}>
          <div className="conflict-dot"></div>
          <span>{activeConflicts.length} конфликтов</span>
        </div>
        <button className="btn" onClick={() => setSidebarOpen(v => !v)}>☰ Детали</button>
      </header>

      {/* Main Body */}
      <div className="app-body">
        <div className="gantt-wrapper">
          <div id="gantt-here-resource" ref={ganttRef}></div>
          <div className="legend-bar">
            <span className="legend-label">Фазы:</span>
            <div className="legend-group">
              <div className="legend-item"><div className="legend-dot" style={{ background: '#8ab4f8' }}></div> А — Анализ</div>
              <div className="legend-item"><div className="legend-dot" style={{ background: '#b69cfa' }}></div> Р — Разработка</div>
              <div className="legend-item"><div className="legend-dot" style={{ background: '#7ec98a' }}></div> Т — Тестирование</div>
              <div className="legend-item"><div className="legend-dot" style={{ background: '#ffb86c' }}></div> О — ОПЭ</div>
            </div>
            <div className="legend-sep" />
            <div className="legend-item"><div className="legend-dot" style={{ background: '#ff4d4f', opacity: 0.7 }}></div> Перегруз</div>
          </div>
        </div>

        <aside className={`sidebar${sidebarOpen ? '' : ' collapsed'}`}>
          <div className="sidebar-header">
            <span className="sidebar-title">{sidebarTitle}</span>
            <button className="sidebar-close" onClick={() => setSidebarOpen(false)}>×</button>
          </div>
          <div className="sidebar-body">
            {sidebarContent ? (
              <div className="dhtmlx-resource-mode" style={{ display: 'contents' }} dangerouslySetInnerHTML={{ __html: sidebarContent }} />
            ) : (
              <div className="sidebar-empty">
                <div className="sidebar-empty-icon">📋</div>
                <div>Выберите инициативу<br />в диаграмме</div>
              </div>
            )}
          </div>
        </aside>
      </div>

      <div className="toast-container" ref={toastContainerRef}></div>
    </div>
  );
}
