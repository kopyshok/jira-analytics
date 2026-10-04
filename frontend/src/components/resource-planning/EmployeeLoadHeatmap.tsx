import { Fragment, useMemo, useState } from 'react';
import { Button, Tooltip } from 'antd';

import type {
  AssignmentOut, EmployeeLoadDay, EmployeeLoadOut, EmployeeQuarterLoad, ExternalBookingOut, WatchRowOut,
} from '../../api/resourcePlanning';
import { dayTooltipLines } from '../../utils/rpBusy';
import { EXT_LOAD_COLOR, NORMED_WORK_COLOR, splitLoadFill } from '../../utils/heatmapFill';
import { dayReserveTypes, fmtHours, reserveUseLines, type ReserveLine } from '../../utils/normedReserve';
import { freeByMonthLabel, techReserveText } from '../../utils/rpWatch';

export interface EmployeeLoadHeatmapProps {
  rows: EmployeeLoadOut[];
  /**
   * Сотрудник -> его группы внутри команды (первая — главная). Пусто —
   * команда не делится, строки идут сплошным списком, как раньше.
   *
   * План остаётся общекомандным сознательно: занятость человека считается
   * сквозь все группы, иначе перегруз в соседней группе не виден. Строка
   * человека — одна, под его главной группой; при делении между группами
   * рядом с именем показывается пометка «общий».
   */
  subgroupByEmployee?: Record<string, string[]>;
  /** Порядок групп; «Без группы» всегда последняя. */
  subgroupOrder?: string[];
  /** Фазы плана — подсказка дня: часы и задачи этого плана. */
  assignments?: AssignmentOut[];
  /** Брони людей плана в других командах — строки подсказки по командам. */
  bookings?: ExternalBookingOut[];
  /** Люди в фильтре «Исполнители» — их имена выделены. */
  selectedIds?: string[];
  /** Щелчок по имени — добавить человека в фильтр или убрать. */
  onEmployeeClick?: (employeeId: string) => void;
  /** Наблюдаемые (список наблюдения плана) — секция под людьми плана. */
  watchRows?: WatchRowOut[];
  /** Брони наблюдаемых в других командах — строки подсказки дня. */
  watchBookings?: ExternalBookingOut[];
  /** Убрать человека из наблюдаемых. */
  onRemoveWatch?: (employeeId: string) => void;
  /** Кнопка «Подобрать людей» в шапке. */
  onPickPeople?: () => void;
}

const RU_MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const RU_WD = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

const CELL = 15; // ширина/высота клетки дня
const CELL_GAP = 2; // зазор между днями внутри недели
const WEEK_GAP = 7; // зазор между неделями
const LABEL_W = 210;
const ROW_H = 26;
const TIP_MAX_W = 420; // ширина подсказки дня: строки длиннее переносятся
// Колонки справа у наблюдаемых: свободно по месяцам и остаток «Технических задач».
const FREE_W = 170;
const TECH_W = 140;
const WATCH_GAP = 10;
// Колонки справа прилипают к правому краю: квартал шире экрана, а свободное
// время — главное, ради чего человек в списке.
const WATCH_RIGHT: React.CSSProperties = {
  display: 'flex',
  gap: WATCH_GAP,
  flexShrink: 0,
  position: 'sticky',
  right: 0,
  zIndex: 1,
  marginLeft: 8,
  padding: '0 4px 0 10px',
  background: '#0f2340',
  boxShadow: '-6px 0 8px -4px rgba(0,0,0,0.5)',
};

// Штриховка отпуска (синеватая) и праздника (тусклая серая).
const ABSENCE_FILL =
  'repeating-linear-gradient(45deg, rgba(116,150,224,0.7) 0 3px, rgba(116,150,224,0.22) 3px 6px)';
const HOLIDAY_FILL =
  'repeating-linear-gradient(45deg, rgba(255,255,255,0.16) 0 3px, rgba(255,255,255,0.04) 3px 6px)';
// Дни вне участия в команде — человека в этом периоде в команде просто нет.
const OUT_OF_TEAM_FILL =
  'repeating-linear-gradient(45deg, rgba(250,173,20,0.5) 0 3px, rgba(250,173,20,0.12) 3px 6px)';

// Стабильные пустые значения по умолчанию.
const NO_ASSIGNMENTS: AssignmentOut[] = [];
const NO_BOOKINGS: ExternalBookingOut[] = [];
const NO_IDS: string[] = [];
const NO_WATCH: WatchRowOut[] = [];

function isoDate(s: string): Date {
  return new Date(s + 'T00:00:00');
}

/** «2026-08-11» → «11.08». */
function fmtDM(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

/** День накануне: «2026-08-11» → «2026-08-10» (без сдвига часовых поясов). */
function prevDayIso(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

/** Подпись под фамилией: с какого дня в команде и до какого — в этом квартале. */
function moveNote(row: EmployeeLoadOut): string {
  const parts: string[] = [];
  if (row.joined_from) {
    const d = fmtDM(row.joined_from.date);
    parts.push(row.joined_from.team ? `в команде с ${d} (из ${row.joined_from.team})` : `в команде с ${d}`);
  }
  if (row.left_to) {
    // Дата перехода — первый день вне команды; показываем последний день в ней.
    const d = fmtDM(prevDayIso(row.left_to.date));
    parts.push(row.left_to.team ? `до ${d}, далее → ${row.left_to.team}` : `до ${d}, далее вне команд`);
  }
  return parts.join(' · ');
}

/** Подпись привлечённого: из какой он команды. */
function borrowedNote(row: EmployeeLoadOut): string {
  return row.borrowed_from ? `из ${row.borrowed_from}` : 'из другой команды';
}

/** Подпись наблюдаемого: основная команда и занят ли он в этом плане. */
function watchNote(w: WatchRowOut): string {
  const home = w.home_team ? `основная — ${w.home_team}` : 'вне команд';
  return w.in_plan ? `${home} · в этом плане` : home;
}

/** Подсказка у остатка «Технических задач»: общий на роль запас основной команды. */
function techTitle(w: WatchRowOut): string {
  const r = w.tech_reserve;
  if (!r) return 'У основной команды нет запаса «Технических задач» для этой роли';
  const used = r.blocked_hours + r.other_teams_hours;
  return `«${r.label}» основной команды${w.home_team ? ` (${w.home_team})` : ''}, общий на роль: `
    + `заложено ${fmtHours(r.planned_hours)}, занято ${fmtHours(used)}, `
    + (r.overuse_hours > 0.05 ? `сверх запаса ${fmtHours(r.overuse_hours)}` : `осталось ${fmtHours(r.remaining_hours)}`);
}

interface EmpRow {
  row: EmployeeLoadOut;
  byDate: Map<string, EmployeeLoadDay>;
  allEmpty: boolean;
}

/** Клетки строки по датам оси и признак «нет загрузки в квартале». */
function toEmpRow(r: EmployeeLoadOut, dates: string[]): EmpRow {
  const byDate = new Map(r.days.map((d) => [d.date, d] as const));
  const allEmpty = dates.every((ds) => {
    const d = byDate.get(ds);
    return !d || d.off || (d.pct <= 0 && !((d.ext_pct ?? 0) > 0) && !((d.normed_pct ?? 0) > 0));
  });
  return { row: r, byDate, allEmpty };
}

/** Текст подсказки для дня вне команды. */
function outOfTeamText(row: EmployeeLoadOut, date: string): string {
  if (row.left_to && date >= row.left_to.date) {
    return `не в команде · с ${fmtDM(row.left_to.date)} — ${row.left_to.team ?? 'вне команд'}`;
  }
  if (row.joined_from && date < row.joined_from.date) {
    return `не в команде · до ${fmtDM(row.joined_from.date)} — ${row.joined_from.team ?? 'вне команд'}`;
  }
  return 'вне команды';
}

/** Строка подсказки: текст или строка запаса с красной частью «сверх запаса». */
type TipLine = string | (ReserveLine & { indent?: boolean });

function TipLineView({ line, bold }: { line: TipLine; bold?: boolean }) {
  if (typeof line === 'string') return <div style={bold ? { fontWeight: 600 } : undefined}>{line}</div>;
  return (
    <div style={line.indent ? { paddingLeft: 12 } : undefined}>
      {line.text}
      {line.over && <span style={{ color: '#ff7875', fontWeight: 600 }}> {line.over}</span>}
    </div>
  );
}

/** Подсказка у имени: разбивка загрузки за квартал; слой «Другие команды» —
 *  с запасом основной команды, за счёт которого он идёт. ``ownLabel`` — чей свой
 *  слой: у людей плана «Задачи плана», у наблюдаемых — основной команды и плана. */
function quarterTooltipLines(q: EmployeeQuarterLoad, ownLabel = 'Задачи плана'): TipLine[] {
  const lines: TipLine[] = [
    `${ownLabel} ${fmtHours(q.own_hours)} · Другие команды ${fmtHours(q.other_teams_hours)} · Нормированные работы ${fmtHours(q.normed_hours)}`,
  ];
  // Часы вне основной команды человека — в плане любой команды одни и те же.
  const uses = q.reserve_use ?? [];
  reserveUseLines(uses).forEach((l, i) =>
    lines.push({ ...l, text: `вне основной команды ${fmtHours(uses[i].hours)} — ${l.text}`, indent: true }),
  );
  for (const t of q.normed_by_type) lines.push({ text: `${t.label} — ${fmtHours(t.hours)}`, indent: true });
  if (q.unplaced_hours > 0.5) lines.push(`Не вмещается ${fmtHours(q.unplaced_hours)}`);
  lines.push(`Норма квартала ${fmtHours(q.capacity_hours)}`);
  return lines;
}

/** Цвет клетки рабочего дня по загрузке. */
function loadColor(pct: number): { bg: string; border?: string } {
  if (pct <= 0) {
    // Свободный рабочий день: чуть заметная заливка (есть ресурс, нет задач).
    return { bg: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)' };
  }
  if (pct > 110) {
    const t = Math.min((pct - 110) / 40, 1);
    const h = 38 - 36 * t; // янтарь → красный
    return { bg: `hsl(${h} 82% 52%)` };
  }
  const t = Math.min(pct, 110) / 110;
  const light = 24 + 26 * t;
  const sat = 28 + 46 * t;
  return { bg: `hsl(150 ${sat}% ${light}%)` };
}

type Off = 'weekend' | 'holiday' | 'absence' | 'out_of_team' | null | undefined;

interface Day {
  date: string;
  dow: number; // 0=Вс
}

interface Week {
  days: Day[];
  monthLabel: string | null;
}

export default function EmployeeLoadHeatmap({
  rows,
  subgroupByEmployee,
  subgroupOrder = [],
  assignments = NO_ASSIGNMENTS,
  bookings = NO_BOOKINGS,
  selectedIds = NO_IDS,
  onEmployeeClick,
  watchRows = NO_WATCH,
  watchBookings = NO_BOOKINGS,
  onRemoveWatch,
  onPickPeople,
}: EmployeeLoadHeatmapProps) {
  const [tip, setTip] = useState<{ left?: number; right?: number; top: number; lines: TipLine[] } | null>(null);

  const data = useMemo(() => {
    if (rows.length === 0) return null;

    // Признак выходного — глобальный (из календаря, одинаков для всех).
    const offByDate = new Map<string, Off>();
    for (const d of rows[0].days) offByDate.set(d.date, d.off);

    // Ось дней без выходных, по возрастанию.
    const dates = Array.from(new Set(rows.flatMap((r) => r.days.map((d) => d.date))))
      .filter((ds) => offByDate.get(ds) !== 'weekend')
      .sort();
    if (dates.length === 0) return null;

    // Недели (по понедельникам) для зазоров и шапки-месяцев.
    const weeks: Week[] = [];
    let seenMonth = -1;
    for (const ds of dates) {
      const dt = isoDate(ds);
      const dow = dt.getDay();
      const m = dt.getMonth();
      if (weeks.length === 0 || dow === 1) {
        const monthLabel = m !== seenMonth ? RU_MONTHS_SHORT[m].toUpperCase() : null;
        if (m !== seenMonth) seenMonth = m;
        weeks.push({ days: [], monthLabel });
      } else if (m !== seenMonth && weeks[weeks.length - 1].monthLabel === null) {
        weeks[weeks.length - 1].monthLabel = RU_MONTHS_SHORT[m].toUpperCase();
        seenMonth = m;
      }
      weeks[weeks.length - 1].days.push({ date: ds, dow });
    }

    const empRows = rows.map((r) => toEmpRow(r, dates));
    const hasExt = rows.some((r) => r.days.some((d) => (d.ext_pct ?? 0) > 0));
    const hasNormed = rows.some((r) => r.days.some((d) => (d.normed_pct ?? 0) > 0));

    const first = isoDate(dates[0]);
    const last = isoDate(dates[dates.length - 1]);
    const periodLabel = `${first.getDate()} ${RU_MONTHS_SHORT[first.getMonth()]} – ${last.getDate()} ${RU_MONTHS_SHORT[last.getMonth()]}`;
    return { weeks, dates, empRows, periodLabel, hasExt, hasNormed };
  }, [rows]);

  // Наблюдаемые — на той же оси дней; порядок с сервера (самые свободные сверху).
  const watchItems = useMemo(
    () => (data ? watchRows.map((r) => toEmpRow(r, data.dates)) : []),
    [data, watchRows],
  );

  // Привлечённые из других команд — отдельная секция внизу.
  const BORROWED = 'Привлечённые';
  const borrowedIds = useMemo(
    () => new Set(rows.filter((r) => r.is_borrowed).map((r) => r.employee_id)),
    [rows],
  );
  const hasSubgroups = Object.keys(subgroupByEmployee ?? {}).length > 0;
  const grouped = hasSubgroups || borrowedIds.size > 0;
  // Главная группа — первая в списке (сервер отдаёт по убыванию доли).
  const groupOf = (employeeId: string) =>
    borrowedIds.has(employeeId) ? BORROWED : (subgroupByEmployee?.[employeeId]?.[0] ?? '');
  const sectionTitle = (group: string) => group || (hasSubgroups ? 'Без группы' : 'Команда');

  // Порядок групп из реестра; «Без группы» — после них, «Привлечённые» — в самом конце.
  const orderedRows = useMemo(() => {
    const empRows = data?.empRows ?? [];
    if (!grouped) return empRows;
    const rank = new Map(subgroupOrder.map((name, i) => [name, i]));
    return [...empRows].sort((a, b) => {
      const ga = groupOf(a.row.employee_id);
      const gb = groupOf(b.row.employee_id);
      const rankOf = (g: string) =>
        g === BORROWED
          ? subgroupOrder.length + 2
          : g
            ? (rank.get(g) ?? subgroupOrder.length)
            : subgroupOrder.length + 1;
      const ra = rankOf(ga);
      const rb = rankOf(gb);
      if (ra !== rb) return ra - rb;
      return (a.row.employee_name ?? '').localeCompare(b.row.employee_name ?? '');
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, grouped, subgroupByEmployee, subgroupOrder, borrowedIds]);

  if (!data) return null;

  const showTip = (
    e: React.MouseEvent, row: EmployeeLoadOut, date: string, off: Off, rowBookings: ExternalBookingOut[],
  ) => {
    const dt = isoDate(date);
    const head = `${RU_WD[dt.getDay()]}, ${dt.getDate()} ${RU_MONTHS_SHORT[dt.getMonth()]}`;
    let body: TipLine[];
    if (off === 'out_of_team') body = [outOfTeamText(row, date)];
    else if (off === 'absence') body = ['отпуск / отсутствие'];
    else if (off === 'holiday') body = ['праздник'];
    else {
      // По строке на этот план и на каждую другую команду: часы и задачи дня.
      const day = row.days.find((d) => d.date === date);
      const lines: TipLine[] = dayTooltipLines(
        row.employee_id, date, assignments, rowBookings, day?.normed_hours ?? 0, day?.blocked,
      );
      // Часы в других командах — за счёт запаса основной команды: строка на вид задач дня.
      const types = dayReserveTypes(row.employee_id, date, row.quarter?.reserve_items, assignments, rowBookings);
      lines.push(...reserveUseLines(row.quarter?.reserve_use, types));
      body = lines.length > 0 ? lines : ['нет загрузки'];
    }
    // У правого края экрана подсказка раскрывается влево от курсора, иначе уходит за край.
    const nearRight = e.clientX > window.innerWidth - TIP_MAX_W;
    setTip({
      top: e.clientY + 14,
      ...(nearRight ? { right: window.innerWidth - e.clientX + 12 } : { left: e.clientX + 12 }),
      lines: [head, ...body],
    });
  };

  const renderRow = ({ row, byDate, allEmpty }: EmpRow, ri: number, watch?: WatchRowOut) => {
    const avg = Math.round(row.quarter?.pct ?? 0);
    // Порог перегруза квартала — 100% (у клеток дня, где перегруз бывает
    // обычным делом на один день, шкала другая — см. loadColor).
    const avgColor = avg > 100 ? { bg: 'hsl(4 78% 52%)' } : loadColor(avg);
    // У привлечённого вместо «пришёл / выбыл» — из какой он команды.
    const note = watch ? watchNote(watch) : row.is_borrowed ? borrowedNote(row) : moveNote(row);
    // Наблюдаемых щелчок по имени в фильтр «Исполнители» не добавляет.
    const click = watch ? undefined : onEmployeeClick;
    // Больше одной группы — пометка «общий», строка всё равно одна.
    const employeeGroups = watch ? [] : (subgroupByEmployee?.[row.employee_id] ?? []);
    const group = groupOf(row.employee_id);
    const prev = watch || ri === 0 ? null : groupOf(orderedRows[ri - 1].row.employee_id);
    const header = !watch && grouped && group !== prev ? (
      <div
        style={{
          width: LABEL_W,
          position: 'sticky',
          left: 0,
          padding: '8px 0 2px',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.06em',
          color: '#7a9ab8',
        }}
      >
        {sectionTitle(group).toUpperCase()}
      </div>
    ) : null;
    return (
      <Fragment key={`${watch ? 'watch' : 'sec'}-${row.employee_id}`}>
      {header}
      <div
        key={row.employee_id}
        style={{
          display: 'flex',
          alignItems: 'center',
          height: note ? ROW_H + 12 : ROW_H,
          background: ri % 2 === 0 ? 'rgba(0,201,200,0.03)' : 'transparent',
        }}
      >
        {/* Левая колонка */}
        <div
          style={{
            width: LABEL_W,
            flexShrink: 0,
            position: 'sticky',
            left: 0,
            background: ri % 2 === 0 ? '#0f2541' : '#0f2340',
            zIndex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            paddingRight: 8,
            height: '100%',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
              <span
                role={click ? 'button' : undefined}
                tabIndex={click ? 0 : undefined}
                aria-pressed={click ? selectedIds.includes(row.employee_id) : undefined}
                onClick={click ? () => click(row.employee_id) : undefined}
                onKeyDown={click ? (e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    click(row.employee_id);
                  }
                } : undefined}
                title={
                  click
                    ? 'Щёлкните, чтобы добавить человека в фильтр «Исполнители» или убрать'
                    : undefined
                }
                style={{
                  fontSize: 12,
                  color: selectedIds.includes(row.employee_id) ? '#00c9c8' : '#fff',
                  fontWeight: selectedIds.includes(row.employee_id) ? 700 : undefined,
                  cursor: click ? 'pointer' : undefined,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {row.employee_name ?? row.employee_id}
              </span>
              {employeeGroups.length > 1 && (
                <span
                  title={`Работает в группах: ${employeeGroups.join(', ')}`}
                  style={{
                    flexShrink: 0,
                    fontSize: 9,
                    lineHeight: '13px',
                    padding: '0 4px',
                    borderRadius: 3,
                    color: '#b39ddb',
                    background: 'rgba(179,157,219,0.16)',
                    border: '1px solid rgba(179,157,219,0.4)',
                  }}
                >
                  общий
                </span>
              )}
            </div>
            {note && (
              <span
                title={note}
                style={{
                  fontSize: 10,
                  color: watch || row.is_borrowed ? '#b39ddb' : '#e0a84a',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {note}
              </span>
            )}
          </div>
          {row.employee_role && (
            <span style={{ fontSize: 10, color: '#5a8ab8', flexShrink: 0 }}>{row.employee_role}</span>
          )}
          {avg > 0 && (
            <Tooltip
              title={row.quarter ? (
                <div style={{ fontSize: 12 }}>
                  {quarterTooltipLines(row.quarter, watch ? 'Задачи основной команды и этого плана' : undefined)
              .map((line, i) => <TipLineView key={i} line={line} />)}
                </div>
              ) : undefined}
              styles={{ root: { maxWidth: TIP_MAX_W } }}
            >
            <span
              style={{
                marginLeft: 'auto',
                flexShrink: 0,
                fontSize: 10,
                fontWeight: 600,
                padding: '1px 6px',
                borderRadius: 8,
                color: avg > 60 ? '#0a1422' : '#cfe',
                background: avgColor.bg,
              }}
            >
              {avg}%
            </span>
            </Tooltip>
          )}
        </div>

        {/* Клетки дней или подпись «нет загрузки» */}
        {allEmpty && !watch ? (
          <div style={{ fontSize: 11, fontStyle: 'italic', color: '#4a6a8a', paddingLeft: 4 }}>
            нет загрузки в этом квартале
          </div>
        ) : (
          data.weeks.map((w, wi) => (
            <div key={wi} style={{ display: 'flex', marginLeft: wi === 0 ? 0 : WEEK_GAP }}>
              {w.days.map((cell) => {
                const d = byDate.get(cell.date);
                const off = d?.off;
                const pct = d?.pct ?? 0;
                const ext = d?.ext_pct ?? 0;
                const normed = d?.normed_pct ?? 0;
                let bg: string;
                let border: string | undefined;
                if (off === 'out_of_team') bg = OUT_OF_TEAM_FILL;
                else if (off === 'absence') bg = ABSENCE_FILL;
                else if (off === 'holiday') bg = HOLIDAY_FILL;
                else {
                  // Снизу — часы в планах других команд, над ними — этот план
                  // цветом общей загрузки дня, выше — нормированные работы
                  // (заблокированный день уже даёт normed 100%).
                  const c = loadColor(pct + ext + normed);
                  bg = splitLoadFill(c.bg, pct, ext, normed);
                  border = ext > 0 || normed > 0 ? undefined : c.border;
                }
                return (
                  <div
                    key={cell.date}
                    onMouseEnter={(e) => showTip(e, row, cell.date, off, watch ? watchBookings : bookings)}
                    onMouseLeave={() => setTip(null)}
                    onMouseOver={(e) => {
                      (e.currentTarget as HTMLDivElement).style.filter = 'brightness(1.25)';
                    }}
                    onMouseOut={(e) => {
                      (e.currentTarget as HTMLDivElement).style.filter = 'none';
                    }}
                    style={{
                      width: CELL,
                      height: CELL,
                      boxSizing: 'border-box',
                      marginRight: CELL_GAP,
                      borderRadius: 3,
                      background: bg,
                      border,
                      cursor: 'default',
                      transition: 'filter 160ms cubic-bezier(0.22,1,0.36,1)',
                    }}
                  />
                );
              })}
            </div>
          ))
        )}
      {watch && renderWatchRight(watch)}
      </div>
      </Fragment>
    );
  };

  // Справа у наблюдаемого: свободно по месяцам и остаток «Технических задач» основной.
  const renderWatchRight = (w: WatchRowOut) => {
    const tech = techReserveText(w.tech_reserve);
    return (
      <div style={{ ...WATCH_RIGHT, alignItems: 'center', height: '100%', fontSize: 11 }}>
        <span
          title={`Свободно за квартал ${fmtHours(w.free_hours)}: норма минус задачи всех команд и нормированные работы`}
          style={{ width: FREE_W, color: '#cfe1f5', whiteSpace: 'nowrap' }}
        >
          {freeByMonthLabel(w.free_by_month)}
        </span>
        <span
          title={techTitle(w)}
          style={{
            width: TECH_W,
            whiteSpace: 'nowrap',
            color: tech.over ? '#ff7875' : '#cfe1f5',
            fontWeight: tech.over ? 600 : undefined,
          }}
        >
          {tech.text}
        </span>
        {onRemoveWatch && (
          <button
            type="button"
            aria-label={`Убрать из наблюдаемых: ${w.employee_name ?? ''}`}
            title="Убрать из наблюдаемых"
            onClick={() => onRemoveWatch(w.employee_id)}
            style={{ background: 'none', border: 'none', color: '#7a9ab8', cursor: 'pointer', fontSize: 14, padding: '0 4px' }}
          >
            ×
          </button>
        )}
      </div>
    );
  };

  // Шапка секции «Наблюдаемые»: подписи колонок справа — над их значениями.
  const watchHeader = (
    <div style={{ display: 'flex', alignItems: 'flex-end', padding: '10px 0 2px' }}>
      <div
        title="Люди любых команд, которых рассматриваете для плана. Свой цвет — задачи их основной команды и этого плана, нижний слой — другие команды. Самые свободные — сверху."
        style={{
          width: LABEL_W,
          flexShrink: 0,
          position: 'sticky',
          left: 0,
          zIndex: 1,
          background: '#0f2340',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.06em',
          color: '#b39ddb',
        }}
      >
        НАБЛЮДАЕМЫЕ
      </div>
      {data.weeks.map((w, wi) => (
        <div key={wi} style={{ display: 'flex', marginLeft: wi === 0 ? 0 : WEEK_GAP }}>
          {w.days.map((d) => (
            <div key={d.date} style={{ width: CELL, marginRight: CELL_GAP }} />
          ))}
        </div>
      ))}
      <div style={{ ...WATCH_RIGHT, fontSize: 10, fontWeight: 600, letterSpacing: '0.04em', color: '#7a9ab8' }}>
        <span style={{ width: FREE_W }}>СВОБОДНО ПО МЕСЯЦАМ, Ч</span>
        <span style={{ width: TECH_W }} title="Остаток «Технических задач» основной команды на роль человека">
          ТЕХ. ЗАДАЧИ ОСНОВНОЙ
        </span>
      </div>
    </div>
  );

  return (
    <div
      style={{
        background: '#0f2340',
        border: '1px solid #1e3a5f',
        borderRadius: 8,
        padding: 12,
        marginTop: 16,
        position: 'relative',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Загрузка сотрудников по дням</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {onPickPeople && (
            <Button
              size="small"
              onClick={onPickPeople}
              title="Добавить людей любых команд секцией «Наблюдаемые» — видно, кто свободен"
            >
              Подобрать людей
            </Button>
          )}
          <div style={{ fontSize: 11, color: 'var(--text-muted, #7a9ab8)' }}>{data.periodLabel}</div>
        </div>
      </div>
      <div style={{ fontSize: 11, color: '#5a7a9a', marginBottom: 8 }}>
        Только рабочие дни. Нормированные работы — запас квартала из сценария основной команды: заблокированные периоды, остаток дня после вовлечённости и остальное — на свободные дни. Процент у имени — загрузка за квартал с задачами других команд и нормированными работами. Наведите на день — часы; на процент у имени — разбивка; щелчок по имени — фильтр по человеку.
      </div>

      <div style={{ overflowX: 'auto' }}>
        <div style={{ display: 'inline-block', minWidth: '100%' }}>
          {/* Шапка: месяцы */}
          <div style={{ display: 'flex', alignItems: 'flex-end', height: 18 }}>
            <div
              style={{
                width: LABEL_W,
                flexShrink: 0,
                position: 'sticky',
                left: 0,
                background: '#0f2340',
                zIndex: 2,
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.06em',
                color: '#7a9ab8',
              }}
            >
              СОТРУДНИК
            </div>
            {data.weeks.map((w, wi) => (
              <div key={wi} style={{ display: 'flex', marginLeft: wi === 0 ? 0 : WEEK_GAP, position: 'relative' }}>
                {w.monthLabel && (
                  <div
                    style={{
                      position: 'absolute',
                      bottom: 0,
                      left: 0,
                      whiteSpace: 'nowrap',
                      fontSize: 10,
                      fontWeight: 600,
                      letterSpacing: '0.06em',
                      color: '#7a9ab8',
                    }}
                  >
                    {w.monthLabel}
                  </div>
                )}
                {w.days.map((d) => (
                  <div key={d.date} style={{ width: CELL, marginRight: CELL_GAP }} />
                ))}
              </div>
            ))}
          </div>

          {/* Строки сотрудников; при делении команды — секциями по группам. */}
          {orderedRows.map((item, ri) => renderRow(item, ri))}

          {/* Наблюдаемые — люди любых команд из списка наблюдения плана. */}
          {watchItems.length > 0 && watchHeader}
          {watchItems.map((item, wi) => renderRow(item, wi, item.row as WatchRowOut))}
        </div>
      </div>

      {/* Легенда */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', color: '#7a9ab8' }}>ЗАГРУЗКА</span>
        {[
          { label: 'свободно', fill: loadColor(0).bg, border: loadColor(0).border },
          { label: 'до 60%', fill: loadColor(45).bg },
          { label: '60–90%', fill: loadColor(80).bg },
          { label: '90–110%', fill: loadColor(100).bg },
          { label: 'свыше 110%', fill: loadColor(125).bg },
          { label: 'отпуск', fill: ABSENCE_FILL },
          { label: 'праздник', fill: HOLIDAY_FILL },
          // Двухцветная клетка: низ — другие команды, верх — этот план.
          ...(data.hasExt || watchRows.some((r) => r.days.some((d) => (d.ext_pct ?? 0) > 0))
            ? [
                { label: 'в этом плане', fill: loadColor(80).bg },
                { label: 'в планах других команд', fill: EXT_LOAD_COLOR },
              ]
            : []),
          ...(data.hasNormed || watchRows.some((r) => r.days.some((d) => (d.normed_pct ?? 0) > 0)) ? [{ label: 'нормированные работы', fill: NORMED_WORK_COLOR }] : []),
          // У наблюдаемых свой слой — задачи их основной команды (и этого плана).
          ...(watchRows.length > 0
            ? [{ label: 'у наблюдаемых — задачи основной команды и этого плана', fill: loadColor(80).bg }]
            : []),
        ].map((it) => (
          <span key={it.label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#9ab3cc' }}>
            <span
              style={{ width: 12, height: 12, borderRadius: 3, background: it.fill, border: it.border, display: 'inline-block' }}
            />
            {it.label}
          </span>
        ))}
      </div>

      {tip && (
        <div
          style={{
            position: 'fixed',
            left: tip.left,
            right: tip.right,
            top: tip.top,
            zIndex: 1000,
            pointerEvents: 'none',
            background: '#0a1628',
            border: '1px solid #1e3a5f',
            borderRadius: 6,
            padding: '4px 8px',
            fontSize: 11,
            color: '#e6f0fa',
            maxWidth: TIP_MAX_W,
            whiteSpace: 'normal',
            boxShadow: '0 4px 14px rgba(0,0,0,0.45)',
          }}
        >
          {tip.lines.map((line, i) => <TipLineView key={i} line={line} bold={i === 0} />)}
        </div>
      )}
    </div>
  );
}
