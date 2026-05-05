import { useEffect, useRef, useState, useCallback } from 'react';
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import './resource-centric.css';

// TODO: replace with useGanttProjection data
const INITIATIVES = [
  { id: 'i1',  key: 'RPM-001', name: 'Реестр сделок v2',          color: '#1677ff', progress: 0.45 },
  { id: 'i2',  key: 'RPM-002', name: 'Миграция Bitrix24 API',     color: '#722ed1', progress: 0.20 },
  { id: 'i3',  key: 'RPM-003', name: 'Дашборд продаж',            color: '#13c2c2', progress: 0.70 },
  { id: 'i4',  key: 'RPM-004', name: 'Интеграция с 1С',           color: '#eb2f96', progress: 0.10 },
  { id: 'i5',  key: 'RPM-005', name: 'Личный кабинет клиента',    color: '#fa8c16', progress: 0.60 },
  { id: 'i6',  key: 'RPM-006', name: 'Электронный документооборот', color: '#52c41a', progress: 0.30 },
  { id: 'i7',  key: 'RPM-007', name: 'Мобильное приложение v3',   color: '#fadb14', progress: 0.05 },
  { id: 'i8',  key: 'RPM-008', name: 'Переход на PostgreSQL',      color: '#f5222d', progress: 0.80 },
  { id: 'i9',  key: 'RPM-009', name: 'HR-портал',                 color: '#2f54eb', progress: 0.50 },
  { id: 'i10', key: 'RPM-010', name: 'Аналитика KPI',             color: '#08979c', progress: 0.15 },
] as const;

const ROLES = [
  { id: 'analyst', name: 'Аналитики',    color: '#69b1ff', icon: '🔍' },
  { id: 'dev',     name: 'Разработчики', color: '#b37feb', icon: '💻' },
  { id: 'qa',      name: 'Тестировщики', color: '#95de64', icon: '🧪' },
  { id: 'ope',     name: 'ОПЭ',          color: '#ffa940', icon: '🚀' },
] as const;

const EMPLOYEES = [
  { id: 'e_a1', name: 'Смирнова А.Д.',  role: 'analyst', capacity: 8, parent: 'g_analyst' },
  { id: 'e_a2', name: 'Козлов П.В.',    role: 'analyst', capacity: 8, parent: 'g_analyst' },
  { id: 'e_a3', name: 'Новикова Е.С.',  role: 'analyst', capacity: 6, parent: 'g_analyst' },
  { id: 'e_d1', name: 'Петров И.А.',    role: 'dev',     capacity: 8, parent: 'g_dev' },
  { id: 'e_d2', name: 'Иванова М.Н.',   role: 'dev',     capacity: 8, parent: 'g_dev' },
  { id: 'e_d3', name: 'Федоров К.Г.',   role: 'dev',     capacity: 8, parent: 'g_dev' },
  { id: 'e_d4', name: 'Соколов В.Р.',   role: 'dev',     capacity: 8, parent: 'g_dev' },
  { id: 'e_d5', name: 'Лебедева О.М.',  role: 'dev',     capacity: 6, parent: 'g_dev' },
  { id: 'e_q1', name: 'Морозова Д.В.',  role: 'qa',      capacity: 8, parent: 'g_qa' },
  { id: 'e_q2', name: 'Волков С.Т.',    role: 'qa',      capacity: 8, parent: 'g_qa' },
  { id: 'e_q3', name: 'Попова Н.И.',    role: 'qa',      capacity: 8, parent: 'g_qa' },
  { id: 'e_o1', name: 'Орлов Б.Д.',     role: 'ope',     capacity: 8, parent: 'g_ope' },
  { id: 'e_o2', name: 'Крылова Т.А.',   role: 'ope',     capacity: 8, parent: 'g_ope' },
];

const PHASE_META: Record<string, { label: string; barColor: string; textColor: string }> = {
  'А': { label: 'Анализ',        barColor: '#2563d4', textColor: '#a8c8ff' },
  'Р': { label: 'Разработка',    barColor: '#6d28d9', textColor: '#c4b5fd' },
  'Т': { label: 'Тестирование',  barColor: '#16a34a', textColor: '#86efac' },
  'О': { label: 'ОПЭ',           barColor: '#b45309', textColor: '#fcd34d' },
};

const TASKS_RAW = [
  { id: 't01', emp: 'e_a1', init: 'i1',  phase: 'А', start: '2026-07-01', end: '2026-07-18', conflict: false },
  { id: 't02', emp: 'e_a1', init: 'i3',  phase: 'А', start: '2026-07-21', end: '2026-08-08', conflict: false },
  { id: 't03', emp: 'e_a1', init: 'i6',  phase: 'А', start: '2026-08-10', end: '2026-09-05', conflict: true  },
  { id: 't04', emp: 'e_a2', init: 'i2',  phase: 'А', start: '2026-07-01', end: '2026-07-25', conflict: false },
  { id: 't05', emp: 'e_a2', init: 'i4',  phase: 'А', start: '2026-07-28', end: '2026-08-28', conflict: false },
  { id: 't06', emp: 'e_a3', init: 'i9',  phase: 'А', start: '2026-07-01', end: '2026-08-15', conflict: false },
  { id: 't07', emp: 'e_a3', init: 'i10', phase: 'А', start: '2026-08-18', end: '2026-09-30', conflict: false },
  { id: 't08', emp: 'e_d1', init: 'i1',  phase: 'Р', start: '2026-07-20', end: '2026-08-20', conflict: false },
  { id: 't09', emp: 'e_d1', init: 'i8',  phase: 'Р', start: '2026-08-05', end: '2026-09-10', conflict: true  },
  { id: 't10', emp: 'e_d2', init: 'i3',  phase: 'Р', start: '2026-07-01', end: '2026-08-01', conflict: false },
  { id: 't11', emp: 'e_d2', init: 'i5',  phase: 'Р', start: '2026-08-04', end: '2026-09-20', conflict: false },
  { id: 't12', emp: 'e_d3', init: 'i2',  phase: 'Р', start: '2026-07-28', end: '2026-09-05', conflict: false },
  { id: 't13', emp: 'e_d3', init: 'i7',  phase: 'Р', start: '2026-09-01', end: '2026-09-30', conflict: true  },
  { id: 't14', emp: 'e_d4', init: 'i4',  phase: 'Р', start: '2026-08-01', end: '2026-09-15', conflict: false },
  { id: 't15', emp: 'e_d4', init: 'i6',  phase: 'Р', start: '2026-09-10', end: '2026-09-30', conflict: false },
  { id: 't16', emp: 'e_d5', init: 'i9',  phase: 'Р', start: '2026-08-10', end: '2026-09-30', conflict: false },
  { id: 't17', emp: 'e_q1', init: 'i3',  phase: 'Т', start: '2026-07-15', end: '2026-08-05', conflict: false },
  { id: 't18', emp: 'e_q1', init: 'i8',  phase: 'Т', start: '2026-08-01', end: '2026-09-10', conflict: true  },
  { id: 't19', emp: 'e_q2', init: 'i1',  phase: 'Т', start: '2026-08-22', end: '2026-09-20', conflict: false },
  { id: 't20', emp: 'e_q2', init: 'i5',  phase: 'Т', start: '2026-09-15', end: '2026-09-30', conflict: false },
  { id: 't21', emp: 'e_q3', init: 'i2',  phase: 'Т', start: '2026-09-01', end: '2026-09-30', conflict: false },
  { id: 't22', emp: 'e_q3', init: 'i7',  phase: 'Т', start: '2026-09-10', end: '2026-09-30', conflict: false },
  { id: 't23', emp: 'e_o1', init: 'i3',  phase: 'О', start: '2026-08-10', end: '2026-08-31', conflict: false },
  { id: 't24', emp: 'e_o1', init: 'i8',  phase: 'О', start: '2026-09-01', end: '2026-09-30', conflict: false },
  { id: 't25', emp: 'e_o2', init: 'i1',  phase: 'О', start: '2026-09-15', end: '2026-09-30', conflict: false },
  { id: 't26', emp: 'e_o2', init: 'i5',  phase: 'О', start: '2026-09-20', end: '2026-09-30', conflict: false },
];

const initMap: Record<string, typeof INITIATIVES[number]> = {};
INITIATIVES.forEach(i => { initMap[i.id] = i; });
const empMap: Record<string, typeof EMPLOYEES[number]> = {};
EMPLOYEES.forEach(e => { empMap[e.id] = e; });
const roleMap: Record<string, typeof ROLES[number]> = {};
ROLES.forEach(r => { roleMap[r.id] = r; });

function buildGanttData() {
  const tasks: any[] = [];
  let order = 1;

  ROLES.forEach(role => {
    tasks.push({
      id: 'g_' + role.id,
      text: role.name,
      type: 'project',
      open: true,
      render: 'split',
      color: 'transparent',
      _isGroup: true,
      _role: role.id,
      _roleColor: role.color,
      order: order++,
    });

    EMPLOYEES.filter(e => e.role === role.id).forEach(emp => {
      tasks.push({
        id: emp.id,
        text: emp.name,
        type: 'project',
        parent: 'g_' + role.id,
        open: true,
        render: 'split',
        color: 'transparent',
        _isEmployee: true,
        _emp: emp,
        _role: role.id,
        _roleColor: role.color,
        order: order++,
      });

      TASKS_RAW.filter(t => t.emp === emp.id).forEach(t => {
        const init = initMap[t.init];
        const phaseMeta = PHASE_META[t.phase];
        const barColor = phaseMeta ? phaseMeta.barColor : (init?.color ?? '#888');
        tasks.push({
          id: t.id,
          text: t.phase + ' · ' + (init?.name ?? t.init),
          start_date: t.start,
          end_date: t.end,
          parent: emp.id,
          color: barColor,
          _conflict: t.conflict,
          _init: init,
          _phase: t.phase,
          _emp: emp,
          order: order++,
          progress: init?.progress ?? 0,
          readonly: false,
        });
      });
    });
  });

  return { data: tasks, links: [] };
}

export default function ResourceCentricMode() {
  const ganttRef = useRef<HTMLDivElement>(null);
  const toastContainerRef = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarTitle, setSidebarTitle] = useState('Детали инициативы');
  const [sidebarContent, setSidebarContent] = useState<string>('');
  const [scaleActive, setScaleActive] = useState<'week'|'day'|'month'>('week');
  const [activeQuarter, setActiveQuarter] = useState<'Q2'|'Q3'|'Q4'>('Q3');
  const [roleFilter, setRoleFilter] = useState('');
  const [initFilter, setInitFilter] = useState('');

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
    const conflicts = TASKS_RAW.filter(t => t.conflict);
    let html = `<div style="font-size:13px;font-weight:600;color:#ff4d4f;margin-bottom:14px;">⚠ Конфликты перегрузки (${conflicts.length})</div>`;
    conflicts.forEach(t => {
      const init = initMap[t.init];
      const emp = empMap[t.emp];
      html += `<div style="padding:10px 12px;background:rgba(255,77,79,0.08);border:1px solid rgba(255,77,79,0.25);border-radius:6px;margin-bottom:8px;">
        <div style="font-weight:600;color:#e6e6e6;margin-bottom:4px;">${init?.name ?? t.init} · ${t.phase}</div>
        <div style="font-size:11px;color:#8c8c8c;">${emp?.name ?? t.emp} · ${t.start} – ${t.end}</div>
        <div style="font-size:11px;color:#ff4d4f;margin-top:4px;">Перегруз: 11ч из 8ч доступных</div>
      </div>`;
    });
    setSidebarTitle('Конфликты');
    setSidebarContent(html);
    setSidebarOpen(true);
  }, []);

  const showTaskDetail = useCallback((task: any) => {
    const init = task._init ?? {};
    const phase = task._phase;
    const phaseLabels: Record<string, string> = { 'А': 'Анализ', 'Р': 'Разработка', 'Т': 'Тестирование', 'О': 'ОПЭ' };
    const phaseColors: Record<string, string> = { 'А': '#1677ff', 'Р': '#722ed1', 'Т': '#52c41a', 'О': '#fa8c16' };

    const initTasks = TASKS_RAW.filter(t => t.init === (init.id ?? ''));
    const phases = ['А', 'Р', 'Т', 'О'];

    const phaseItems = phases.map(ph => {
      const phaseTasks = initTasks.filter(t => t.phase === ph);
      if (!phaseTasks.length) return '';
      const firstStart = phaseTasks.reduce((a, t) => t.start < a ? t.start : a, phaseTasks[0].start);
      const lastEnd = phaseTasks.reduce((a, t) => t.end > a ? t.end : a, phaseTasks[0].end);
      const hasConflict = phaseTasks.some(t => t.conflict);
      const now = new Date(2026, 6, 15);
      const startD = new Date(firstStart), endD = new Date(lastEnd);
      let status = 'pending', statusLabel = 'Ожидание';
      if (endD < now) { status = 'done'; statusLabel = 'Готово'; }
      else if (startD <= now) { status = 'active'; statusLabel = 'В работе'; }
      if (hasConflict) { status = 'conflict'; statusLabel = 'Конфликт'; }
      return `<div class="phase-item">
        <div class="phase-icon" style="background:${phaseColors[ph]}22;color:${phaseColors[ph]};border:1px solid ${phaseColors[ph]}44;">${ph}</div>
        <div class="phase-info">
          <div class="phase-name">${phaseLabels[ph]}</div>
          <div class="phase-dates">${firstStart.slice(5)} — ${lastEnd.slice(5)}</div>
        </div>
        <div class="phase-status ${status}">${statusLabel}</div>
      </div>`;
    }).join('');

    const assigneeIds = [...new Set(initTasks.map(t => t.emp))];
    const chipHtml = assigneeIds.map(eid => {
      const e = empMap[eid];
      if (!e) return '';
      const r = roleMap[e.role];
      const initials = e.name.split(' ').map((p: string) => p[0]).join('').slice(0,2);
      return `<div class="assignee-chip"><div class="chip-avatar" style="background:${r?.color ?? '#888'}cc">${initials}</div><span>${e.name}</span></div>`;
    }).join('');

    const progressPct = Math.round((init.progress ?? 0) * 100);

    setSidebarTitle(init.name ?? task.text);
    setSidebarContent(`
      <div class="detail-init-color" style="background:${init.color ?? '#1677ff'};"></div>
      <div class="detail-name">${init.name ?? task.text}</div>
      <div class="detail-key">${init.key ?? ''}</div>
      <div class="progress-bar-wrap"><div class="progress-bar-fill" style="width:${progressPct}%;background:${init.color ?? 'var(--accent)'};"></div></div>
      <div style="font-size:11px;color:var(--text-muted);margin:6px 0 16px;text-align:right;">${progressPct}% завершено</div>
      <div class="detail-section">
        <div class="detail-section-title">Параметры</div>
        <div class="detail-row"><span class="detail-label">Статус</span><span class="detail-value" style="color:var(--ok);">В работе</span></div>
        <div class="detail-row"><span class="detail-label">Квартал</span><span class="detail-value">Q3 2026</span></div>
        <div class="detail-row"><span class="detail-label">Фаза выбрана</span><span class="detail-value">${phaseLabels[phase] ?? phase}</span></div>
        ${task._conflict ? `<div class="detail-row"><span class="detail-label" style="color:var(--danger);">⚠ Перегруз</span><span class="detail-value" style="color:var(--danger);">11ч / 8ч</span></div>` : ''}
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
  }, []);

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

    gantt.config.scales = [
      { unit: 'month', step: 1, format: '%F %Y' },
      { unit: 'week',  step: 1, format: 'Нед %W' },
    ] as any;

    gantt.config.start_date = new Date(2026, 6, 1);
    gantt.config.end_date   = new Date(2026, 9, 1);

    gantt.config.columns = [
      {
        name: 'text',
        label: 'Сотрудник / Роль',
        width: 210,
        tree: true,
        template: (task: any) => {
          if (task._isGroup) {
            const role = roleMap[task._role];
            return `<div class="group-cell"><div class="role-dot" style="background:${role?.color}"></div><span>${role?.icon} ${role?.name}</span></div>`;
          }
          if (task._isEmployee) {
            const emp = task._emp;
            const role = roleMap[emp.role];
            const initials = emp.name.split(' ').map((p: string) => p[0]).join('').slice(0,2);
            return `<div class="employee-cell"><div class="emp-avatar" style="background:${role?.color}cc">${initials}</div><div class="emp-info"><div class="emp-name">${emp.name}</div><div class="emp-role">${role?.name}</div></div></div>`;
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
      const init = task._init;
      return `<span style="opacity:0.85;">${task._phase}</span> ${init?.name ?? task.text}`;
    };

    gantt.templates.tooltip_text = (_start: any, _end: any, task: any) => {
      if (task._isGroup || task._isEmployee) return '';
      const init = task._init ?? {};
      const phase = PHASE_META[task._phase] ?? {};
      let html = `<div style="min-width:200px;">
        <div style="font-weight:700;color:#e6e6e6;margin-bottom:6px;">${init.name ?? task.text}</div>
        <div style="color:#8c8c8c;font-size:11px;margin-bottom:4px;">Фаза: <span style="color:#e6e6e6;">${task._phase} — ${(phase as any).label ?? ''}</span></div>
        <div style="color:#8c8c8c;font-size:11px;margin-bottom:4px;">Прогресс: ${Math.round((task.progress||0)*100)}%</div>`;
      if (task._conflict) {
        html += `<div style="color:#ff4d4f;font-weight:600;margin-top:8px;padding:6px 8px;background:rgba(255,77,79,0.1);border-radius:4px;border:1px solid rgba(255,77,79,0.3);">⚠ Перегруз: 11ч из 8ч доступных</div>`;
      }
      html += '</div>';
      return html;
    };

    gantt.templates.task_row_class = (_start: any, _end: any, task: any) => {
      if (!task._isEmployee) return '';
      const empId = task.id;
      const hasConflict = TASKS_RAW.some(t => t.emp === empId && t.conflict);
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
      if (mode === 'move') {
        showToast('✅', `Назначено · ${task._init?.name ?? ''}`);
      }
    });

    gantt.attachEvent('onTaskClick', (id: any) => {
      const task = gantt.getTask(id);
      if (task._isGroup || task._isEmployee) return true;
      showTaskDetail(task);
      return true;
    });

    gantt.attachEvent('onBeforeLightbox', () => false);

    gantt.init(ganttRef.current);
    gantt.parse(buildGanttData());

    return () => {
      try { gantt.clearAll(); } catch { /* ignore */ }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const setQuarterRange = (q: 'Q2'|'Q3'|'Q4') => {
    setActiveQuarter(q);
    if (q === 'Q2') { gantt.config.start_date = new Date(2026, 3, 1); gantt.config.end_date = new Date(2026, 6, 1); }
    else if (q === 'Q3') { gantt.config.start_date = new Date(2026, 6, 1); gantt.config.end_date = new Date(2026, 9, 1); }
    else { gantt.config.start_date = new Date(2026, 9, 1); gantt.config.end_date = new Date(2027, 0, 1); }
    gantt.render();
  };

  const applyFilter = (newRole?: string, newInit?: string) => {
    const r = newRole !== undefined ? newRole : roleFilter;
    const initId = newInit !== undefined ? newInit : initFilter;
    (gantt as any).filter_task = (_id: any, task: any) => {
      if (task._isGroup) { if (r && task._role !== r) return false; return true; }
      if (task._isEmployee) { if (r && task._role !== r) return false; return true; }
      if (r && task._emp && task._emp.role !== r) return false;
      if (initId && task._init && task._init.id !== initId) return false;
      return true;
    };
    gantt.render();
  };

  return (
    <div className="dhtmlx-resource-mode" style={{ position: 'relative' }}>
      {/* App Header */}
      <header className="app-header">
        <div className="app-header__logo">
          <div className="app-header__icon">📅</div>
          <div>
            <div className="app-header__title">Планирование ресурсов · Ресурсо-центричный</div>
            <div className="app-header__subtitle">Квартальный план · Q3 2026</div>
          </div>
        </div>
        <div className="header-divider" />
        <div className="header-controls">
          <div className="quarter-selector">
            {(['Q2','Q3','Q4'] as const).map(q => (
              <button key={q} className={`quarter-btn${activeQuarter === q ? ' active' : ''}`} onClick={() => setQuarterRange(q)}>{q}</button>
            ))}
          </div>
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
            <option value="ope">ОПЭ</option>
          </select>
          <select className="select-control" value={initFilter} onChange={e => { setInitFilter(e.target.value); applyFilter(undefined, e.target.value); }}>
            <option value="">Все инициативы</option>
            {INITIATIVES.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
          <button className="btn" onClick={() => (gantt as any).collapseAll()}>⊟ Свернуть</button>
          <button className="btn" onClick={() => (gantt as any).expandAll()}>⊞ Развернуть</button>
        </div>
        <div className="header-spacer" />
        <div className="conflict-badge" onClick={showConflictPanel}>
          <div className="conflict-dot"></div>
          <span>5 конфликтов</span>
        </div>
        <button className="btn btn--primary" onClick={() => showToast('🚀', 'Solver запущен — оптимизация...')}>⚡ Solver</button>
        <button className="btn" onClick={() => setSidebarOpen(v => !v)}>☰ Детали</button>
      </header>

      {/* Main Body */}
      <div className="app-body">
        <div className="gantt-wrapper">
          <div id="gantt-here-resource" ref={ganttRef}></div>
          <div className="legend-bar">
            <span className="legend-label">Фазы:</span>
            <div className="legend-group">
              <div className="legend-item"><div className="legend-dot" style={{ background:'#8ab4f8' }}></div> А — Анализ</div>
              <div className="legend-item"><div className="legend-dot" style={{ background:'#b69cfa' }}></div> Р — Разработка</div>
              <div className="legend-item"><div className="legend-dot" style={{ background:'#7ec98a' }}></div> Т — Тестирование</div>
              <div className="legend-item"><div className="legend-dot" style={{ background:'#ffb86c' }}></div> О — ОПЭ</div>
            </div>
            <div className="legend-sep" />
            <span className="legend-label">Роли:</span>
            <div className="legend-group">
              <div className="legend-item"><div className="legend-dot" style={{ background:'#69b1ff' }}></div> Аналитик</div>
              <div className="legend-item"><div className="legend-dot" style={{ background:'#b37feb' }}></div> Разработчик</div>
              <div className="legend-item"><div className="legend-dot" style={{ background:'#95de64' }}></div> Тестировщик</div>
              <div className="legend-item"><div className="legend-dot" style={{ background:'#ffa940' }}></div> ОПЭ</div>
            </div>
            <div className="legend-sep" />
            <div className="legend-item"><div className="legend-dot" style={{ background:'#ff4d4f', opacity:0.7 }}></div> Перегруз</div>
          </div>
        </div>

        <aside className={`sidebar${sidebarOpen ? '' : ' collapsed'}`}>
          <div className="sidebar-header">
            <span className="sidebar-title">{sidebarTitle}</span>
            <button className="sidebar-close" onClick={() => setSidebarOpen(false)}>×</button>
          </div>
          <div className="sidebar-body">
            {sidebarContent ? (
              <div dangerouslySetInnerHTML={{ __html: sidebarContent }} />
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
