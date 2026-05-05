import { useEffect, useRef, useState } from 'react';
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import './classic.css';

// TODO: replace with useGanttProjection data
const COLORS = {
  analyst: '#5b8dee',
  dev:     '#36cfc9',
  qa:      '#9254de',
  ope:     '#fa8c16',
  summary: '#3a4a5a',
};

const TASKS_DATA = {
  data: [
    // ── 1. Реестр сделок v2
    { id:1,  text:'Реестр сделок v2',        start_date:'01-07-2026', duration:65, type:'project', open:true, progress:0.3 },
    { id:11, text:'Анализ требований',        start_date:'01-07-2026', duration:12, parent:1, role:'analyst', color:COLORS.analyst, assignees:'Петрова А., Белова С.', progress:0.9, est_h:96 },
    { id:12, text:'Разработка бэкенда',       start_date:'14-07-2026', duration:25, parent:1, role:'dev',     color:COLORS.dev,     assignees:'Смирнов К., Козлов Д.', progress:0.5, est_h:200 },
    { id:13, text:'Тестирование',             start_date:'08-08-2026', duration:14, parent:1, role:'qa',      color:COLORS.qa,      assignees:'Новикова Е.',           progress:0.1, est_h:112 },
    { id:14, text:'ОПЭ',                      start_date:'22-08-2026', duration:14, parent:1, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:56  },
    // ── 2. Миграция Bitrix24 API
    { id:2,  text:'Миграция Bitrix24 API',   start_date:'07-07-2026', duration:55, type:'project', open:true, progress:0.2 },
    { id:21, text:'Аудит API v1',             start_date:'07-07-2026', duration:10, parent:2, role:'analyst', color:COLORS.analyst, assignees:'Белова С.',              progress:0.8, est_h:80 },
    { id:22, text:'Разработка адаптера',      start_date:'17-07-2026', duration:28, parent:2, role:'dev',     color:COLORS.dev,     assignees:'Смирнов К., Лебедев П.', progress:0.3, est_h:224, conflict:true },
    { id:23, text:'Интеграционное тестир.',   start_date:'14-08-2026', duration:12, parent:2, role:'qa',      color:COLORS.qa,      assignees:'Новикова Е.',           progress:0,   est_h:96  },
    { id:24, text:'ОПЭ Bitrix',               start_date:'26-08-2026', duration:10, parent:2, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:40  },
    // ── 3. Дашборд продаж
    { id:3,  text:'Дашборд продаж',          start_date:'14-07-2026', duration:50, type:'project', open:true, progress:0.15 },
    { id:31, text:'UX-аналитика',             start_date:'14-07-2026', duration:10, parent:3, role:'analyst', color:COLORS.analyst, assignees:'Петрова А.',            progress:0.6, est_h:80, conflict:true },
    { id:32, text:'Frontend-разработка',      start_date:'24-07-2026', duration:22, parent:3, role:'dev',     color:COLORS.dev,     assignees:'Лебедев П., Фёдоров Т.', progress:0.2, est_h:176 },
    { id:33, text:'Тестирование дашборда',    start_date:'15-08-2026', duration:10, parent:3, role:'qa',      color:COLORS.qa,      assignees:'Захаров В.',            progress:0,   est_h:80  },
    { id:34, text:'ОПЭ дашборда',             start_date:'25-08-2026', duration:7,  parent:3, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:28, conflict:true },
    // ── 4. Интеграция с 1С
    { id:4,  text:'Интеграция с 1С',         start_date:'21-07-2026', duration:60, type:'project', open:true, progress:0.1 },
    { id:41, text:'Аналитика маппинга',       start_date:'21-07-2026', duration:12, parent:4, role:'analyst', color:COLORS.analyst, assignees:'Петрова А., Белова С.', progress:0.5, est_h:96 },
    { id:42, text:'Разработка коннектора',    start_date:'02-08-2026', duration:30, parent:4, role:'dev',     color:COLORS.dev,     assignees:'Смирнов К., Козлов Д.', progress:0,   est_h:240, conflict:true },
    { id:43, text:'Функциональное тестир.',   start_date:'01-09-2026', duration:12, parent:4, role:'qa',      color:COLORS.qa,      assignees:'Новикова Е.',           progress:0,   est_h:96  },
    { id:44, text:'ОПЭ 1С',                   start_date:'13-09-2026', duration:14, parent:4, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:56, conflict:true },
    // ── 5. Мобильный клиент v3
    { id:5,  text:'Мобильный клиент v3',     start_date:'01-07-2026', duration:75, type:'project', open:true, progress:0.35 },
    { id:51, text:'Спецификация функций',     start_date:'01-07-2026', duration:10, parent:5, role:'analyst', color:COLORS.analyst, assignees:'Белова С.',              progress:1.0, est_h:80 },
    { id:52, text:'iOS + Android',            start_date:'11-07-2026', duration:40, parent:5, role:'dev',     color:COLORS.dev,     assignees:'Козлов Д., Фёдоров Т.', progress:0.4, est_h:320, conflict:true },
    { id:53, text:'Мобильное тестирование',   start_date:'20-08-2026', duration:15, parent:5, role:'qa',      color:COLORS.qa,      assignees:'Новикова Е., Захаров В.', progress:0,   est_h:120, conflict:true },
    { id:54, text:'ОПЭ мобильного клиента',  start_date:'04-09-2026', duration:12, parent:5, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:48  },
    // ── 6. Портальный мониторинг
    { id:6,  text:'Портальный мониторинг',   start_date:'14-07-2026', duration:55, type:'project', open:false, progress:0.05 },
    { id:61, text:'Аналитика метрик',         start_date:'14-07-2026', duration:8,  parent:6, role:'analyst', color:COLORS.analyst, assignees:'Белова С.',              progress:0.7, est_h:64 },
    { id:62, text:'Разработка сервисов',      start_date:'22-07-2026', duration:28, parent:6, role:'dev',     color:COLORS.dev,     assignees:'Козлов Д., Лебедев П.', progress:0.1, est_h:224, conflict:true },
    { id:63, text:'Тестирование мониторинга', start_date:'19-08-2026', duration:10, parent:6, role:'qa',      color:COLORS.qa,      assignees:'Захаров В.',            progress:0,   est_h:80  },
    { id:64, text:'ОПЭ мониторинга',          start_date:'29-08-2026', duration:10, parent:6, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:40  },
    // ── 7. Автоматизация отчётности
    { id:7,  text:'Автоматизация отчётности', start_date:'28-07-2026', duration:45, type:'project', open:false, progress:0 },
    { id:71, text:'Аналитика отчётов',        start_date:'28-07-2026', duration:8,  parent:7, role:'analyst', color:COLORS.analyst, assignees:'Петрова А.',            progress:0,   est_h:64 },
    { id:72, text:'ETL-разработка',           start_date:'05-08-2026', duration:22, parent:7, role:'dev',     color:COLORS.dev,     assignees:'Лебедев П.',            progress:0,   est_h:176 },
    { id:73, text:'Тестирование ETL',         start_date:'27-08-2026', duration:10, parent:7, role:'qa',      color:COLORS.qa,      assignees:'Захаров В.',            progress:0,   est_h:80  },
    { id:74, text:'ОПЭ отчётности',           start_date:'06-09-2026', duration:8,  parent:7, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:32  },
    // ── 8. Система уведомлений
    { id:8,  text:'Система уведомлений',     start_date:'21-07-2026', duration:40, type:'project', open:false, progress:0 },
    { id:81, text:'Аналитика каналов',        start_date:'21-07-2026', duration:7,  parent:8, role:'analyst', color:COLORS.analyst, assignees:'Белова С.',              progress:0,   est_h:56 },
    { id:82, text:'Push + Email сервис',      start_date:'28-07-2026', duration:20, parent:8, role:'dev',     color:COLORS.dev,     assignees:'Фёдоров Т.',            progress:0,   est_h:160 },
    { id:83, text:'Тестирование уведомлений', start_date:'17-08-2026', duration:8,  parent:8, role:'qa',      color:COLORS.qa,      assignees:'Захаров В.',            progress:0,   est_h:64  },
    { id:84, text:'ОПЭ уведомлений',          start_date:'25-08-2026', duration:7,  parent:8, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:28  },
    // ── 9. Онбординг нового персонала
    { id:9,  text:'Онбординг нового персонала', start_date:'01-08-2026', duration:45, type:'project', open:false, progress:0 },
    { id:91, text:'Аналитика процессов',      start_date:'01-08-2026', duration:7,  parent:9, role:'analyst', color:COLORS.analyst, assignees:'Петрова А.',            progress:0,   est_h:56 },
    { id:92, text:'HR-портал разработка',     start_date:'08-08-2026', duration:20, parent:9, role:'dev',     color:COLORS.dev,     assignees:'Лебедев П.',            progress:0,   est_h:160 },
    { id:93, text:'Тестирование портала',     start_date:'28-08-2026', duration:10, parent:9, role:'qa',      color:COLORS.qa,      assignees:'Захаров В.',            progress:0,   est_h:80  },
    { id:94, text:'ОПЭ HR-портала',           start_date:'07-09-2026', duration:10, parent:9, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',              progress:0,   est_h:40  },
    // ── 10. Архив документов
    { id:10, text:'Архив документов ЭДО',    start_date:'14-08-2026', duration:38, type:'project', open:false, progress:0 },
    { id:101,text:'Аналитика хранилища',     start_date:'14-08-2026', duration:7,  parent:10, role:'analyst', color:COLORS.analyst, assignees:'Белова С.',             progress:0,   est_h:56 },
    { id:102,text:'Разработка архива',       start_date:'21-08-2026', duration:18, parent:10, role:'dev',     color:COLORS.dev,     assignees:'Козлов Д.',            progress:0,   est_h:144 },
    { id:103,text:'Тестирование архива',     start_date:'08-09-2026', duration:10, parent:10, role:'qa',      color:COLORS.qa,      assignees:'Новикова Е.',          progress:0,   est_h:80  },
    { id:104,text:'ОПЭ архива',              start_date:'18-09-2026', duration:8,  parent:10, role:'ope',     color:COLORS.ope,     assignees:'Орлов М.',             progress:0,   est_h:32  },
  ] as any[],
  links: [
    { id:1,  source:11, target:12, type:'0' },
    { id:2,  source:12, target:13, type:'0' },
    { id:3,  source:13, target:14, type:'0' },
    { id:4,  source:21, target:22, type:'0' },
    { id:5,  source:22, target:23, type:'0' },
    { id:6,  source:23, target:24, type:'0' },
    { id:7,  source:31, target:32, type:'0' },
    { id:8,  source:32, target:33, type:'0' },
    { id:9,  source:33, target:34, type:'0' },
    { id:10, source:41, target:42, type:'0' },
    { id:11, source:42, target:43, type:'0' },
    { id:12, source:43, target:44, type:'0' },
    { id:13, source:51, target:52, type:'0' },
    { id:14, source:52, target:53, type:'0' },
    { id:15, source:53, target:54, type:'0' },
    { id:16, source:61, target:62, type:'0' },
    { id:17, source:62, target:63, type:'0' },
    { id:18, source:63, target:64, type:'0' },
    { id:19, source:71, target:72, type:'0' },
    { id:20, source:72, target:73, type:'0' },
    { id:21, source:73, target:74, type:'0' },
    { id:22, source:81, target:82, type:'0' },
    { id:23, source:82, target:83, type:'0' },
    { id:24, source:83, target:84, type:'0' },
    { id:25, source:91, target:92, type:'0' },
    { id:26, source:92, target:93, type:'0' },
    { id:27, source:93, target:94, type:'0' },
    { id:28, source:101,target:102,type:'0' },
    { id:29, source:102,target:103,type:'0' },
    { id:30, source:103,target:104,type:'0' },
    { id:31, source:14, target:31, type:'0' },
    { id:32, source:24, target:41, type:'0' },
  ],
};

// TODO: replace with useGanttProjection data
const EMP_LOAD: Record<string, number[]> = {
  'r1':  [70,160,100, 80, 70, 90, 80, 70, 90, 60, 50, 40],
  'r2':  [80, 90, 70, 80, 70, 60, 70, 80, 60, 50, 60, 50],
  'r3':  [60,100,180,110, 80, 70, 80, 60, 70, 50, 40, 30],
  'r4':  [70, 80, 90, 90,140,100, 80, 70, 60, 50, 40, 30],
  'r5':  [50, 70, 80, 90, 80, 90, 80, 70, 60, 50, 40, 30],
  'r6':  [40, 60, 80, 90, 70, 80, 70, 60, 50, 40, 30, 20],
  'r7':  [30, 40, 50, 60, 70, 80,170, 90,150,100, 70, 50],
  'r8':  [40, 50, 60, 70, 80, 90, 80, 90, 70, 80, 60, 50],
  'r9':  [20, 30, 40, 50, 60, 70, 80,150,140,160, 80, 60],
  'r10': [30, 50, 70, 80, 90, 80, 70, 60, 50, 40, 30, 20],
  'r11': [20, 30, 40, 50, 60, 70, 80, 90, 70, 60, 50, 40],
  'r12': [50, 60, 70, 80, 70, 60, 50, 40, 60, 70, 60, 50],
  'r13': [40, 60, 80, 70, 80, 70, 60, 50, 40, 30, 20, 10],
  'r14': [30, 40, 50, 60, 70, 80, 90, 80, 70, 60, 50, 40],
  'r15': [10, 20, 30, 40, 50, 60, 70, 80,100, 90, 60, 40],
};

const RESOURCES = [
  { id:'r1',  name:'Петрова А.',    role:'analyst', role_label:'Аналитик',    capacity:8, color:COLORS.analyst },
  { id:'r2',  name:'Белова С.',     role:'analyst', role_label:'Аналитик',    capacity:8, color:COLORS.analyst },
  { id:'r3',  name:'Смирнов К.',    role:'dev',     role_label:'Разработчик', capacity:8, color:COLORS.dev     },
  { id:'r4',  name:'Козлов Д.',     role:'dev',     role_label:'Разработчик', capacity:8, color:COLORS.dev     },
  { id:'r5',  name:'Лебедев П.',    role:'dev',     role_label:'Разработчик', capacity:8, color:COLORS.dev     },
  { id:'r6',  name:'Фёдоров Т.',    role:'dev',     role_label:'Разработчик', capacity:8, color:COLORS.dev     },
  { id:'r7',  name:'Новикова Е.',   role:'qa',      role_label:'QA',          capacity:8, color:COLORS.qa      },
  { id:'r8',  name:'Захаров В.',    role:'qa',      role_label:'QA',          capacity:8, color:COLORS.qa      },
  { id:'r9',  name:'Орлов М.',      role:'ope',     role_label:'ОПЭ',         capacity:8, color:COLORS.ope     },
  { id:'r10', name:'Иванов И.',     role:'dev',     role_label:'Разработчик', capacity:8, color:COLORS.dev     },
  { id:'r11', name:'Сидорова Н.',   role:'qa',      role_label:'QA',          capacity:8, color:COLORS.qa      },
  { id:'r12', name:'Кузнецов А.',   role:'analyst', role_label:'Аналитик',    capacity:8, color:COLORS.analyst },
  { id:'r13', name:'Морозов С.',    role:'dev',     role_label:'Разработчик', capacity:8, color:COLORS.dev     },
  { id:'r14', name:'Попова М.',     role:'qa',      role_label:'QA',          capacity:8, color:COLORS.qa      },
  { id:'r15', name:'Волков Г.',     role:'ope',     role_label:'ОПЭ',         capacity:8, color:COLORS.ope     },
];

const WEEK_LABELS = ['6/7','13/7','20/7','27/7','3/8','10/8','17/8','24/8','31/8','7/9','14/9','21/9'];

function buildResourceView(containerId: string) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';

  const ROW_H = 26;
  const LABEL_W = 160;
  const CELL_W = 44;
  const numWeeks = 12;
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

  // Header background
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

  WEEK_LABELS.forEach((wl, wi) => {
    const x = LABEL_W + wi * CELL_W + CELL_W / 2;
    const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('x', String(x)); t.setAttribute('y', String(headerH / 2 + 4));
    t.setAttribute('text-anchor', 'middle'); t.setAttribute('fill', '#8c8c8c');
    t.setAttribute('font-size', '9'); t.setAttribute('font-family', 'Segoe UI, system-ui');
    t.textContent = wl;
    svg.appendChild(t);
  });

  const hdrLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  hdrLine.setAttribute('x1', '0'); hdrLine.setAttribute('y1', String(headerH));
  hdrLine.setAttribute('x2', String(totalW)); hdrLine.setAttribute('y2', String(headerH));
  hdrLine.setAttribute('stroke', '#303030'); hdrLine.setAttribute('stroke-width', '1');
  svg.appendChild(hdrLine);

  RESOURCES.forEach((res, ri) => {
    const loads = EMP_LOAD[res.id] || [];
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

    const roleText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    roleText.setAttribute('x', String(LABEL_W - 4)); roleText.setAttribute('y', String(rowY + ROW_H / 2 + 4));
    roleText.setAttribute('text-anchor', 'end'); roleText.setAttribute('fill', res.color);
    roleText.setAttribute('font-size', '9'); roleText.setAttribute('font-family', 'Segoe UI, system-ui');
    roleText.textContent = res.role_label;
    svg.appendChild(roleText);

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
}

export default function ClassicMode() {
  const ganttRef = useRef<HTMLDivElement>(null);
  const [conflictVisible, setConflictVisible] = useState(false);
  const [scale, setScale] = useState('week');
  const [quarter, setQuarter] = useState('q3-2026');
  const [team, setTeam] = useState('all');
  const splitterRef = useRef<HTMLDivElement>(null);
  const resourceContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ganttRef.current) return;

    // Reset to baseline config
    gantt.clearAll();

    // Plugins
    try {
      gantt.plugins({ marker: true, tooltip: true } as any);
    } catch { /* already loaded */ }

    // Russian locale
    try {
      (gantt as any).i18n.setLocale('ru');
    } catch { try { if ((gantt as any).locale_ru) (gantt as any).locale = (gantt as any).locale_ru; } catch { /* skip */ } }

    gantt.config.show_progress = true;
    (gantt.config as any).drag_progress = true;
    gantt.config.drag_resize = true;
    gantt.config.drag_move = true;
    gantt.config.drag_links = true;
    (gantt.config as any).auto_types = true;
    gantt.config.date_format = '%d-%m-%Y';
    gantt.config.start_date = new Date(2026, 6, 1);
    gantt.config.end_date = new Date(2026, 9, 1);
    gantt.config.row_height = 30;
    gantt.config.bar_height = 18;
    gantt.config.scale_height = 46;
    (gantt.config as any).min_column_width = 32;
    gantt.config.fit_tasks = false;
    gantt.config.show_unscheduled = true;
    (gantt.config as any).round_dnd_dates = true;
    gantt.config.open_tree_initially = false;

    gantt.config.columns = [
      { name:'text', label:'Инициатива / Фаза', width:200, tree:true, resize:true },
      {
        name:'role', label:'Роль', width:80, resize:true, align:'center',
        template: (task: any) => {
          const labels: Record<string,string> = { analyst:'Анализ', dev:'Разработка', qa:'QA', ope:'ОПЭ' };
          if (task.type === 'project') return '';
          const l = labels[task.role] || '';
          const c = (COLORS as any)[task.role] || '#888';
          return `<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:${c}22;color:${c};border:1px solid ${c}44">${l}</span>`;
        }
      },
      {
        name:'assignees', label:'Исполнители', width:150, resize:true,
        template: (task: any) => {
          if (task.type === 'project') return '';
          return `<span style="color:#8c8c8c;font-size:11px">${task.assignees || '—'}</span>`;
        }
      },
      {
        name:'est_h', label:'Оценка ч.', width:64, align:'right', resize:true,
        template: (task: any) => {
          if (task.type === 'project') return '';
          const conflict = task.conflict ? '<span style="color:#ff4d4f;margin-left:3px" title="Перегрузка">⚠</span>' : '';
          return `<span style="color:#8c8c8c">${task.est_h || '—'}</span>${conflict}`;
        }
      },
    ] as any;

    gantt.config.scales = [
      { unit:'month', step:1, format:'%F %Y' },
      { unit:'week', step:1, format:(date: Date) => {
        const d = new Date(date);
        const end = new Date(d.getTime() + 6*24*60*60*1000);
        return `${d.getDate()}/${d.getMonth()+1}–${end.getDate()}/${end.getMonth()+1}`;
      }}
    ] as any;

    gantt.templates.task_class = (_start: any, _end: any, task: any) => {
      const cls: string[] = [];
      if (task.conflict) cls.push('conflict-task');
      if (task.type === 'project') cls.push('gantt_project');
      return cls.join(' ');
    };

    gantt.templates.tooltip_text = (_start: any, _end: any, task: any) => {
      if (task.type === 'project') return `<b>${task.text}</b>`;
      const roleLabels: Record<string,string> = { analyst:'Анализ', dev:'Разработка', qa:'Тестирование', ope:'ОПЭ' };
      const pct = Math.round((task.progress || 0) * 100);
      const conflictWarn = task.conflict ? '<div style="color:#ff4d4f;margin-top:6px">⚠ Обнаружен конфликт перегрузки</div>' : '';
      return `<b>${task.text}</b>` +
        `<div style="margin-top:6px;color:#8c8c8c">Роль: ${roleLabels[task.role] || task.role || '—'}</div>` +
        `<div style="color:#8c8c8c">Исполнители: ${task.assignees || '—'}</div>` +
        `<div style="color:#8c8c8c">Оценка: ${task.est_h || '—'} ч.</div>` +
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
    gantt.parse(TASKS_DATA);

    if ((gantt as any).addMarker) {
      (gantt as any).addMarker({ start_date: new Date(2026, 4, 4), css: 'today_line', text: 'Сегодня', title: 'Сегодня' });
      (gantt as any).addMarker({ start_date: new Date(2026, 8, 30), css: 'today_line', text: 'Конец Q3', title: 'Конец квартала' });
    }

    buildResourceView('resource-gantt-container-classic');

    return () => {
      try { gantt.clearAll(); } catch { /* ignore */ }
    };
  }, []);

  // Scale switcher
  const applyScale = (v: string) => {
    setScale(v);
    if (v === 'week') {
      gantt.config.scales = [
        { unit:'month', step:1, format:'%F %Y' },
        { unit:'week', step:1, format:(date: Date) => {
          const d = new Date(date);
          const end = new Date(d.getTime() + 6*24*60*60*1000);
          return `${d.getDate()}/${d.getMonth()+1}–${end.getDate()}/${end.getMonth()+1}`;
        }}
      ] as any;
      (gantt.config as any).min_column_width = 32;
    } else if (v === 'month') {
      gantt.config.scales = [
        { unit:'year', step:1, format:'%Y' },
        { unit:'month', step:1, format:'%M' }
      ] as any;
      (gantt.config as any).min_column_width = 80;
    } else {
      gantt.config.scales = [
        { unit:'week', step:1, format:'Неделя %W' },
        { unit:'day', step:1, format:'%d' }
      ] as any;
      (gantt.config as any).min_column_width = 28;
    }
    gantt.render();
  };

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
          <span className="ctrl-label">Квартал</span>
          <select className="ctrl-select" value={quarter} onChange={e => setQuarter(e.target.value)}>
            <option value="q3-2026">Q3 2026 · Июль – Сентябрь</option>
            <option value="q4-2026">Q4 2026 · Октябрь – Декабрь</option>
            <option value="q1-2027">Q1 2027 · Январь – Март</option>
          </select>
          <div className="header-divider" />
          <span className="ctrl-label">Команда</span>
          <select className="ctrl-select" value={team} onChange={e => setTeam(e.target.value)}>
            <option value="all">Все команды</option>
            <option value="core">Ядро платформы</option>
            <option value="crm">CRM / Продажи</option>
            <option value="mobile">Мобильная разработка</option>
          </select>
          <div className="header-divider" />
          <span className="ctrl-label">Просмотр</span>
          <select className="ctrl-select" value={scale} onChange={e => applyScale(e.target.value)}>
            <option value="week">По неделям</option>
            <option value="month">По месяцам</option>
            <option value="day">По дням</option>
          </select>
        </div>
        <div className="header-spacer" />
        <div className="legend">
          <div className="legend-item"><div className="legend-dot" style={{ background:'#5b8dee' }}></div>Анализ</div>
          <div className="legend-item"><div className="legend-dot" style={{ background:'#36cfc9' }}></div>Разработка</div>
          <div className="legend-item"><div className="legend-dot" style={{ background:'#9254de' }}></div>Тестирование</div>
          <div className="legend-item"><div className="legend-dot" style={{ background:'#fa8c16' }}></div>ОПЭ</div>
        </div>
        <div className="header-divider" />
        <div className="conflict-badge" onClick={() => setConflictVisible(v => !v)}>
          ⚠ 5 конфликтов
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
        <span><span className="status-dot"></span>Q3 2026 · 01.07 – 30.09</span>
        <span>·</span>
        <span>10 инициатив · 38 фаз</span>
        <span>·</span>
        <span>15 сотрудников</span>
        <span>·</span>
        <span style={{ color:'#ff4d4f' }}>5 конфликтов перегрузки</span>
        <div style={{ flex:1 }}></div>
        <span>DHTMLX Gantt Standard (GPL-2.0)</span>
      </div>

      {/* Conflict Panel */}
      <div className={`conflict-panel${conflictVisible ? ' visible' : ''}`}>
        <div className="conflict-panel-header">
          <div className="conflict-panel-title">⚠ Конфликты перегрузки (5)</div>
          <div className="conflict-panel-close" onClick={() => setConflictVisible(false)}>×</div>
        </div>
        <div className="conflict-list">
          <div className="conflict-item">
            <div className="conflict-item-person">Петрова А. · Аналитик</div>
            <div className="conflict-item-dates">14 – 25 июля 2026</div>
            <div className="conflict-item-load">Загрузка 160% · Реестр сделок v2 + Дашборд продаж</div>
          </div>
          <div className="conflict-item">
            <div className="conflict-item-person">Смирнов К. · Разработчик</div>
            <div className="conflict-item-dates">28 июля – 08 августа 2026</div>
            <div className="conflict-item-load">Загрузка 180% · Миграция Bitrix24 + Интеграция с 1С</div>
          </div>
          <div className="conflict-item">
            <div className="conflict-item-person">Козлов Д. · Разработчик</div>
            <div className="conflict-item-dates">11 – 22 августа 2026</div>
            <div className="conflict-item-load">Загрузка 140% · Мобильный клиент v3 + Порт. мониторинг</div>
          </div>
          <div className="conflict-item">
            <div className="conflict-item-person">Новикова Е. · QA</div>
            <div className="conflict-item-dates">25 августа – 05 сентября 2026</div>
            <div className="conflict-item-load">Загрузка 170% · Реестр сделок v2 + Мобильный клиент v3</div>
          </div>
          <div className="conflict-item">
            <div className="conflict-item-person">Орлов М. · ОПЭ</div>
            <div className="conflict-item-dates">15 – 30 сентября 2026</div>
            <div className="conflict-item-load">Загрузка 150% · Интеграция 1С + Дашборд продаж</div>
          </div>
        </div>
      </div>
    </div>
  );
}
