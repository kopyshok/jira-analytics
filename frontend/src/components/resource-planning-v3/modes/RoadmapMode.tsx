import { useEffect, useRef, useState, useCallback } from 'react';
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import './roadmap.css';

// TODO: replace with useGanttProjection data

const Q3_START = new Date(2026, 6, 1);
const currentWeekIdx = 2;

function getWeekNumber(date: Date): number {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + 4 - (d.getDay() || 7));
  const yearStart = new Date(d.getFullYear(), 0, 1);
  return Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
}

const MONTHS = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];

const WEEKS = Array.from({ length: 13 }, (_, i) => {
  const d = new Date(Q3_START);
  d.setDate(d.getDate() + i * 7);
  const end = new Date(d);
  end.setDate(end.getDate() + 6);
  return {
    index: i,
    label: `${d.getDate()} ${MONTHS[d.getMonth()]}`,
    month: MONTHS[d.getMonth()],
    num: `${d.getDate()}–${end.getDate()}`,
    start: new Date(d),
    end,
    isoNum: getWeekNumber(d),
  };
});

const ROLES = [
  { id: 'analyst', label: 'Аналитик',    cls: 'analyst', color: '#69b1ff', count: 4, capacity: 640 },
  { id: 'dev',     label: 'Разработчик', cls: 'dev',     color: '#b37feb', count: 8, capacity: 1280 },
  { id: 'qa',      label: 'Тестировщик', cls: 'qa',      color: '#95de64', count: 3, capacity: 480 },
  { id: 'ope',     label: 'ОПЭ',          cls: 'ope',     color: '#ffa940', count: 2, capacity: 320 },
];

const INITIATIVES = [
  { id:'i1',  name:'Реестр сделок v2',          status:'active', weekStart:0,  weekEnd:6,  roles:['analyst','dev','qa'],       color:'#69b1ff',
    phases:[
      { name:'Анализ требований',  start:'2026-07-01', end:'2026-07-14', type:'analyst', progress:0.9, id:1, deps:[] },
      { name:'Разработка API',     start:'2026-07-13', end:'2026-07-31', type:'dev',     progress:0.6, id:2, deps:[1] },
      { name:'Разработка UI',      start:'2026-07-20', end:'2026-08-07', type:'dev',     progress:0.3, id:3, deps:[1] },
      { name:'Тестирование',       start:'2026-08-03', end:'2026-08-14', type:'qa',      progress:0,   id:4, deps:[2,3] },
      { name:'ОПЭ',                start:'2026-08-11', end:'2026-08-21', type:'ope',     progress:0,   id:5, deps:[4] },
    ], employees:['Иванов А.П.','Смирнова Е.В.','Козлов Д.Н.','Петрова М.С.','Фёдоров О.К.'], critical:[1,2,4,5] },
  { id:'i2',  name:'Миграция Bitrix24 API',      status:'risk',   weekStart:1,  weekEnd:9,  roles:['dev','qa'],                 color:'#b37feb',
    phases:[
      { name:'Аудит текущего API',   start:'2026-07-06', end:'2026-07-17', type:'analyst', progress:0.8, id:1, deps:[] },
      { name:'Разработка адаптера',  start:'2026-07-15', end:'2026-08-14', type:'dev',     progress:0.4, id:2, deps:[1] },
      { name:'Интеграционные тесты', start:'2026-08-10', end:'2026-08-28', type:'qa',      progress:0,   id:3, deps:[2] },
      { name:'Пилотная нагрузка',    start:'2026-08-24', end:'2026-09-04', type:'ope',     progress:0,   id:4, deps:[3] },
    ], employees:['Захаров В.Р.','Новикова Т.А.','Морозов С.П.','Кузнецова И.Г.'], critical:[1,2,3,4] },
  { id:'i3',  name:'Дашборд продаж',             status:'plan',   weekStart:3,  weekEnd:10, roles:['analyst','dev','qa'],       color:'#95de64',
    phases:[
      { name:'UX-исследование',   start:'2026-07-20', end:'2026-07-31', type:'analyst', progress:0.1, id:1, deps:[] },
      { name:'Дизайн и прототип', start:'2026-07-27', end:'2026-08-07', type:'analyst', progress:0,   id:2, deps:[1] },
      { name:'Бэкенд аналитики',  start:'2026-08-03', end:'2026-08-28', type:'dev',     progress:0,   id:3, deps:[1] },
      { name:'Фронтенд дашборда', start:'2026-08-10', end:'2026-09-04', type:'dev',     progress:0,   id:4, deps:[2] },
      { name:'QA + UAT',          start:'2026-08-31', end:'2026-09-11', type:'qa',      progress:0,   id:5, deps:[3,4] },
    ], employees:['Волкова Н.С.','Лебедев Р.О.','Соколова Д.В.','Попов М.Е.','Артемьева К.Ю.'], critical:[1,3,5] },
  { id:'i4',  name:'Интеграция с 1С',            status:'active', weekStart:0,  weekEnd:11, roles:['analyst','dev'],            color:'#ffa940',
    phases:[
      { name:'Спецификация обмена',   start:'2026-07-01', end:'2026-07-10', type:'analyst', progress:1.0, id:1, deps:[] },
      { name:'Разработка коннектора', start:'2026-07-08', end:'2026-08-21', type:'dev',     progress:0.5, id:2, deps:[1] },
      { name:'Тестирование обмена',   start:'2026-08-17', end:'2026-09-04', type:'qa',      progress:0,   id:3, deps:[2] },
      { name:'Продовый запуск',       start:'2026-09-01', end:'2026-09-11', type:'ope',     progress:0,   id:4, deps:[3] },
    ], employees:['Егоров Д.А.','Орлова Ю.В.','Макаров Н.П.','Белова С.Е.'], critical:[1,2,3,4] },
  { id:'i5',  name:'Портал поставщиков',         status:'plan',   weekStart:5,  weekEnd:12, roles:['analyst','dev','qa','ope'], color:'#ff85c2',
    phases:[
      { name:'Анализ процессов',   start:'2026-08-03', end:'2026-08-14', type:'analyst', progress:0, id:1, deps:[] },
      { name:'Разработка портала', start:'2026-08-12', end:'2026-09-11', type:'dev',     progress:0, id:2, deps:[1] },
      { name:'Тестирование',       start:'2026-09-07', end:'2026-09-21', type:'qa',      progress:0, id:3, deps:[2] },
      { name:'ОПЭ',                start:'2026-09-18', end:'2026-09-30', type:'ope',     progress:0, id:4, deps:[3] },
    ], employees:['Тихонов В.А.','Романова О.Н.','Зайцев М.В.','Никитина Е.П.','Павлов С.И.'], critical:[1,2,3,4] },
  { id:'i6',  name:'Автоматизация KYC',          status:'risk',   weekStart:2,  weekEnd:8,  roles:['analyst','dev','qa'],       color:'#ff7875',
    phases:[
      { name:'Регуляторный анализ', start:'2026-07-13', end:'2026-07-24', type:'analyst', progress:0.5, id:1, deps:[] },
      { name:'ML-модель проверки',  start:'2026-07-22', end:'2026-08-21', type:'dev',     progress:0.2, id:2, deps:[1] },
      { name:'Тестирование ML',     start:'2026-08-17', end:'2026-09-04', type:'qa',      progress:0,   id:3, deps:[2] },
    ], employees:['Семёнов К.Л.','Александрова В.Ю.','Громов Р.А.','Котова Д.С.'], critical:[1,2,3] },
  { id:'i7',  name:'Мобильное приложение',       status:'plan',   weekStart:4,  weekEnd:12, roles:['analyst','dev','qa'],       color:'#36cfc9',
    phases:[
      { name:'Продуктовый анализ', start:'2026-07-27', end:'2026-08-07', type:'analyst', progress:0, id:1, deps:[] },
      { name:'iOS / Android',      start:'2026-08-05', end:'2026-09-18', type:'dev',     progress:0, id:2, deps:[1] },
      { name:'QA мобайл',          start:'2026-09-14', end:'2026-09-28', type:'qa',      progress:0, id:3, deps:[2] },
    ], employees:['Дмитриев А.О.','Соловьёв Г.Е.','Мартынова Н.В.','Киселев П.А.'], critical:[1,2,3] },
  { id:'i8',  name:'Рефакторинг авторизации',    status:'active', weekStart:0,  weekEnd:4,  roles:['dev','qa'],                 color:'#b37feb',
    phases:[
      { name:'Аудит кода',   start:'2026-07-01', end:'2026-07-07', type:'analyst', progress:1.0, id:1, deps:[] },
      { name:'Рефакторинг',  start:'2026-07-06', end:'2026-07-25', type:'dev',     progress:0.7, id:2, deps:[1] },
      { name:'Регрессия',    start:'2026-07-23', end:'2026-08-01', type:'qa',      progress:0,   id:3, deps:[2] },
    ], employees:['Андреев В.С.','Степанова Е.А.','Шевченко И.Н.'], critical:[1,2,3] },
  { id:'i9',  name:'Витрина данных EDW',         status:'plan',   weekStart:6,  weekEnd:12, roles:['analyst','dev'],            color:'#69b1ff',
    phases:[
      { name:'Проектирование DWH', start:'2026-08-10', end:'2026-08-21', type:'analyst', progress:0, id:1, deps:[] },
      { name:'ETL-пайплайны',      start:'2026-08-19', end:'2026-09-18', type:'dev',     progress:0, id:2, deps:[1] },
      { name:'Валидация данных',   start:'2026-09-14', end:'2026-09-28', type:'qa',      progress:0, id:3, deps:[2] },
    ], employees:['Кириллов М.А.','Герасимова О.Р.','Беляев Д.Т.'], critical:[1,2,3] },
  { id:'i10', name:'API-шлюз v3',                status:'risk',   weekStart:1,  weekEnd:7,  roles:['dev','qa','ope'],           color:'#ffa940',
    phases:[
      { name:'Архитектура шлюза',    start:'2026-07-06', end:'2026-07-17', type:'analyst', progress:0.6, id:1, deps:[] },
      { name:'Разработка шлюза',     start:'2026-07-15', end:'2026-08-14', type:'dev',     progress:0.3, id:2, deps:[1] },
      { name:'Нагрузочные тесты',    start:'2026-08-10', end:'2026-08-28', type:'qa',      progress:0,   id:3, deps:[2] },
      { name:'Боевая эксплуатация',  start:'2026-08-24', end:'2026-09-04', type:'ope',     progress:0,   id:4, deps:[3] },
    ], employees:['Сидоров П.Н.','Крылова А.М.','Давыдов О.Ф.','Борисова Н.Г.'], critical:[2,3,4] },
] as const;

type Initiative = typeof INITIATIVES[number];

const HEATMAP: Record<string, number[]> = {
  analyst: [72, 85, 110, 95, 88, 105, 92, 78, 65, 72, 80, 75, 68],
  dev:     [88, 115, 108, 95, 102, 98, 85, 90, 88, 72, 68, 75, 65],
  qa:      [45, 50, 60, 78, 92, 115, 108, 95, 88, 72, 65, 58, 52],
  ope:     [30, 35, 42, 50, 65, 72, 88, 102, 108, 95, 78, 65, 55],
};

const ROLE_INITIATIVES: Record<string, string[]> = {
  analyst: ['i1','i3','i4','i6','i9'],
  dev:     ['i1','i2','i4','i7','i8','i10'],
  qa:      ['i2','i3','i6','i8','i10'],
  ope:     ['i4','i5','i10'],
};

const PHASE_COLORS: Record<string, string> = {
  analyst: 'rgba(105,177,255,0.75)',
  dev:     'rgba(179,127,235,0.75)',
  qa:      'rgba(149,222,100,0.75)',
  ope:     'rgba(255,169,64,0.75)',
};

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
  return `${d}-${m}-${y}`;
}

function pctClass(pct: number): string {
  if (pct > 100) return 'hc-over';
  if (pct >= 80)  return 'hc-warn';
  if (pct > 0)    return 'hc-ok';
  return 'hc-empty';
}

export default function RoadmapMode() {
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
  const [, setCurrentInitId] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState('');
  const [activeQuarter, setActiveQuarter] = useState<'Q2 2026'|'Q3 2026'|'Q4 2026'>('Q3 2026');

  const drillGanttInit = useRef(false);

  const showTip = useCallback((e: MouseEvent, init: Initiative) => {
    const tip = customTipRef.current;
    if (!tip) return;
    const startWeek = WEEKS[init.weekStart];
    const endWeek = WEEKS[Math.min(init.weekEnd, 12)];
    tip.querySelector('.custom-tip-name')!.textContent = init.name;
    const rows = tip.querySelectorAll('.custom-tip-row b');
    if (rows[0]) rows[0].textContent = `${startWeek.label} – ${endWeek.label}`;
    if (rows[1]) rows[1].textContent = init.status === 'risk' ? '⚠ Перегруз ролей' : 'В норме';
    if (rows[2]) rows[2].textContent = `~${(init.weekEnd - init.weekStart + 1) * 40} ч`;
    tip.style.display = 'block';
    tip.style.left = `${e.clientX + 12}px`;
    tip.style.top = `${e.clientY - 30}px`;
  }, []);

  const hideTip = useCallback(() => {
    if (customTipRef.current) customTipRef.current.style.display = 'none';
  }, []);

  const loadDrillGantt = useCallback((init: Initiative) => {
    const container = drillGanttRef.current;
    if (!container) return;

    const phases = init.phases as readonly any[];
    const earliest = phases.reduce((m, p) => p.start < m ? p.start : m, phases[0].start);
    const latest   = phases.reduce((m, p) => p.end > m ? p.end : m, phases[0].end);
    const dStart = parseDate(earliest); dStart.setDate(dStart.getDate() - 3);
    const dEnd = parseDate(latest); dEnd.setDate(dEnd.getDate() + 7);

    if (!drillGanttInit.current) {
      try {
        (gantt as any).i18n.setLocale({
          date: {
            month_full: ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'],
            month_short: ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'],
            day_full: ['Воскресенье','Понедельник','Вторник','Среда','Четверг','Пятница','Суббота'],
            day_short: ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'],
          },
          labels: { new_task:'Новая задача', icon_save:'Сохранить', icon_cancel:'Отмена', column_text:'Задача', column_start_date:'Начало', column_duration:'Дней', column_add:'' }
        });
      } catch { /* skip */ }

      gantt.config.readonly = true;
      gantt.config.drag_links = false;
      gantt.config.drag_move = false;
      gantt.config.drag_resize = false;
      gantt.config.scale_height = 46;
      gantt.config.row_height = 28;
      gantt.config.bar_height = 18;
      (gantt.config as any).link_arrow_size = 6;
      gantt.config.date_format = '%d-%m-%Y';

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
          template: (task: any) => {
            if (task.isMilestone) return `<span style="color:#ff4d4f;font-weight:600">◆ ${task.text}</span>`;
            return task.text;
          }
        },
        {
          name: 'duration', label: 'Дн', width: 38, align: 'center',
          template: (task: any) => task.type === (gantt.config as any).types?.milestone ? '' : task.duration,
        },
      ] as any;

      gantt.config.scales = [
        { unit: 'month', step: 1, format: '%F %Y' },
        { unit: 'week',  step: 1, format: (date: Date) => `${date.getDate()} ${MONTHS[date.getMonth()]}` },
      ] as any;

      gantt.templates.task_class = (_s: any, _e: any, task: any) => task.isCritical ? 'gantt-critical' : '';
      gantt.templates.task_text = (_s: any, _e: any, task: any) => {
        const milestoneType = (gantt.config as any).types?.milestone;
        return task.type === milestoneType ? '' : task.text;
      };
      gantt.templates.tooltip_text = (_s: any, _e: any, task: any) => {
        const milestoneType = (gantt.config as any).types?.milestone;
        if (task.type === milestoneType) return `<b>${task.text}</b>`;
        const role = ROLES.find(r => r.id === task.phaseType);
        return `<b>${task.text}</b><br>Роль: ${role?.label ?? '—'}<br>Прогресс: ${Math.round((task.progress||0)*100)}%`;
      };
      gantt.templates.scale_cell_class = (date: Date) => (date.getDay() === 0 || date.getDay() === 6) ? 'gantt_weekend' : '';

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
    const idOffset = 100;

    phases.forEach((phase: any) => {
      const ganttId = idOffset + phase.id;
      const isCrit = (init.critical as readonly number[]).includes(phase.id);
      const bg = isCrit ? 'rgba(255,77,79,0.85)' : PHASE_COLORS[phase.type] ?? '#888';
      tasks.push({
        id: ganttId, text: phase.name,
        start_date: formatGanttDate(parseDate(phase.start)),
        end_date: formatGanttDate(addDay(parseDate(phase.end), 1)),
        progress: phase.progress ?? 0,
        phaseType: phase.type,
        isCritical: isCrit,
        color: bg,
        textColor: isCrit ? '#fff' : '#141414',
      });
      (phase.deps ?? []).forEach((depId: number) => {
        links.push({ id: links.length + 1, source: idOffset + depId, target: ganttId, type: '0' });
      });
    });

    const lastCritPhase = [...phases]
      .filter((p: any) => (init.critical as readonly number[]).includes(p.id))
      .sort((a: any, b: any) => b.end.localeCompare(a.end))[0];

    if (lastCritPhase) {
      const msDate = parseDate(lastCritPhase.end);
      msDate.setDate(msDate.getDate() + 1);
      tasks.push({
        id: 999, text: 'Завершение',
        start_date: formatGanttDate(msDate),
        end_date: formatGanttDate(addDay(msDate, 1)),
        type: (gantt.config as any).types?.milestone ?? 'milestone',
        isMilestone: true, color: '#ff4d4f',
      });
      links.push({ id: links.length + 1, source: idOffset + lastCritPhase.id, target: 999, type: '0' });
    }

    gantt.parse({ data: tasks, links });
  }, []);

  const openDrill = useCallback((id: string) => {
    const init = INITIATIVES.find(x => x.id === id);
    if (!init) return;
    setCurrentInitId(id);
    setDrillTitle(init.name);
    const startWeek = WEEKS[init.weekStart];
    const endWeek = WEEKS[Math.min(init.weekEnd, 12)];
    setDrillMeta(`${startWeek.label} – ${endWeek.label} · ${init.employees.length} сотрудников`);
    setBreadcrumb(init.name);
    setDrillOpen(true);
    // Highlight active card
    sidebarListRef.current?.querySelectorAll('.init-card').forEach(c => c.classList.remove('active'));
    sidebarListRef.current?.querySelector(`#card-${id}`)?.classList.add('active');
    setTimeout(() => loadDrillGantt(init), drillGanttInit.current ? 50 : 100);
  }, [loadDrillGantt]);

  const closeDrill = useCallback(() => {
    setDrillOpen(false);
    setBreadcrumb(null);
    setCurrentInitId(null);
    sidebarListRef.current?.querySelectorAll('.init-card').forEach(c => c.classList.remove('active'));
    try { gantt.clearAll(); } catch { /* ignore */ }
    drillGanttInit.current = false;
  }, []);

  // Build week headers
  useEffect(() => {
    const container = weekHeadersRef.current;
    if (!container) return;
    container.innerHTML = '';
    WEEKS.forEach((w, i) => {
      const el = document.createElement('div');
      el.className = 'week-col' + (i === currentWeekIdx ? ' current-week' : '');
      el.innerHTML = `<div class="wc-month">${w.month}</div><div class="wc-num">${w.num}</div>`;
      container.appendChild(el);
    });
  }, []);

  // Build swimlanes
  useEffect(() => {
    const container = swimlanesRef.current;
    if (!container) return;
    container.innerHTML = '';

    ROLES.forEach(role => {
      const lane = document.createElement('div');
      lane.className = 'swimlane';

      const roleCol = document.createElement('div');
      roleCol.className = 'swimlane-role-col';
      roleCol.innerHTML = `
        <div class="role-badge ${role.cls}">${role.label}</div>
        <div class="role-meta"><b>${role.count}</b> чел · <b>${role.capacity}</b> ч/кв</div>
      `;
      lane.appendChild(roleCol);

      const chart = document.createElement('div');
      chart.className = 'swimlane-chart';

      const heatRow = document.createElement('div');
      heatRow.className = 'heatmap-row';
      WEEKS.forEach((_, i) => {
        const pct = HEATMAP[role.id][i];
        const cell = document.createElement('div');
        cell.className = 'heatmap-cell ' + pctClass(pct);
        cell.setAttribute('data-pct', String(pct));
        cell.title = `Нед ${i+1}: ${pct}%`;
        heatRow.appendChild(cell);
      });
      chart.appendChild(heatRow);

      const initRow = document.createElement('div');
      initRow.className = 'initiatives-row';

      const roleInits = (ROLE_INITIATIVES[role.id] ?? [])
        .map(id => INITIATIVES.find(x => x.id === id))
        .filter(Boolean) as Initiative[];

      const layoutRows: Initiative[][] = [];
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
          const bar = document.createElement('div');
          bar.className = 'init-bar';
          bar.style.left = `${(init.weekStart / 13) * 100}%`;
          bar.style.width = `${((init.weekEnd - init.weekStart + 1) / 13) * 100}%`;
          bar.style.background = init.color + 'cc';
          bar.style.color = '#141414';
          bar.style.top = rowIdx === 0 ? '6px' : '30px';
          bar.textContent = init.name;
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
  }, [openDrill, showTip, hideTip]);

  // Build sidebar cards
  const renderSidebarCards = useCallback((inits: readonly Initiative[]) => {
    const list = sidebarListRef.current;
    if (!list) return;
    list.innerHTML = '';
    const statusLabel: Record<string, string> = { active:'В работе', plan:'Плановая', risk:'Под риском' };
    const statusCls: Record<string, string>   = { active:'status-active', plan:'status-plan', risk:'status-risk' };
    inits.forEach((init, idx) => {
      const card = document.createElement('div');
      card.className = 'init-card';
      card.id = `card-${init.id}`;
      (card as HTMLElement).style.animationDelay = `${idx * 0.04}s`;
      const startWeek = WEEKS[init.weekStart];
      const endWeek = WEEKS[Math.min(init.weekEnd, 12)];
      const dateRange = `${startWeek.label} – ${endWeek.label}`;
      const roleDots = [...new Set(init.roles)].map(r => {
        const role = ROLES.find(x => x.id === r);
        return `<div class="role-dot" style="background:${role?.color}" title="${role?.label}"></div>`;
      }).join('');
      card.innerHTML = `
        <div class="init-card-name">${init.name}</div>
        <div class="init-card-meta">${roleDots}<div class="init-card-dates">${dateRange}</div><div class="init-card-status ${statusCls[init.status]}">${statusLabel[init.status]}</div></div>
        <button class="drill-btn" data-id="${init.id}">Детали ›</button>
      `;
      card.addEventListener('click', (e) => {
        if ((e.target as Element).tagName === 'BUTTON') { openDrill(init.id); return; }
        openDrill(init.id);
      });
      list.appendChild(card);
    });
  }, [openDrill]);

  useEffect(() => {
    renderSidebarCards(INITIATIVES);
  }, [renderSidebarCards]);

  // Search
  useEffect(() => {
    if (!searchQ.trim()) { renderSidebarCards(INITIATIVES); return; }
    const filtered = INITIATIVES.filter(i => i.name.toLowerCase().includes(searchQ.toLowerCase()));
    renderSidebarCards(filtered);
  }, [searchQ, renderSidebarCards]);

  // Cleanup drill gantt on unmount
  useEffect(() => {
    return () => {
      try { gantt.clearAll(); } catch { /* ignore */ }
      drillGanttInit.current = false;
    };
  }, []);

  return (
    <div className="dhtmlx-roadmap-mode">
      {/* Header */}
      <header className="app-header">
        <div className="header-logo">RPM<span>·</span>Plan</div>
        <div className="header-sep" />
        <div className="breadcrumb">
          {breadcrumb ? (
            <>
              <span style={{ cursor:'pointer', color:'var(--text-muted)' }} onClick={closeDrill}>Roadmap</span>
              <span className="crumb-sep">›</span>
              <span className="crumb-active">{breadcrumb}</span>
            </>
          ) : (
            <span className="crumb-active">Roadmap</span>
          )}
        </div>
        <div className="header-spacer" />
        <div className="legend-pills">
          <div className="legend-pill"><div className="legend-dot" style={{ background:'var(--load-ok)' }}></div><span>&lt;80%</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background:'var(--load-warn)' }}></div><span>80–100%</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background:'var(--load-over)' }}></div><span>&gt;100%</span></div>
          <div className="header-sep" />
          <div className="legend-pill"><div className="legend-dot" style={{ background:'var(--analyst)' }}></div><span>Аналитик</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background:'var(--dev)' }}></div><span>Разработчик</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background:'var(--qa)' }}></div><span>QA</span></div>
          <div className="legend-pill"><div className="legend-dot" style={{ background:'var(--ope)' }}></div><span>ОПЭ</span></div>
        </div>
        <div className="header-sep" />
        <div className="quarter-switcher">
          {(['Q2 2026','Q3 2026','Q4 2026'] as const).map(q => (
            <button key={q} className={`quarter-btn${activeQuarter === q ? ' active' : ''}`} onClick={() => setActiveQuarter(q)}>{q}</button>
          ))}
        </div>
      </header>

      {/* Main layout: roadmap + sidebar */}
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
            <div className="sidebar-title">Инициативы · Q3 2026</div>
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
            <div className="dl-item"><div className="dl-swatch" style={{ background:'rgba(105,177,255,0.7)' }}></div>Анализ</div>
            <div className="dl-item"><div className="dl-swatch" style={{ background:'rgba(179,127,235,0.7)' }}></div>Разработка</div>
            <div className="dl-item"><div className="dl-swatch" style={{ background:'rgba(149,222,100,0.7)' }}></div>Тестирование</div>
            <div className="dl-item"><div className="dl-swatch" style={{ background:'rgba(255,169,64,0.7)' }}></div>ОПЭ</div>
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
        <div className="custom-tip-row"><span>Загрузка</span><b></b></div>
        <div className="custom-tip-row"><span>Часов</span><b></b></div>
      </div>
    </div>
  );
}
