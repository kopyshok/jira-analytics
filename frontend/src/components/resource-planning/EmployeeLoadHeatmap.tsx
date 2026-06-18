import { useMemo, useState } from 'react';

import type { EmployeeLoadOut } from '../../api/resourcePlanning';

interface Props {
  rows: EmployeeLoadOut[];
}

const RU_MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const RU_WD = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

const CELL = 15; // ширина/высота клетки дня
const CELL_GAP = 2; // зазор между днями внутри недели
const WEEK_GAP = 7; // зазор между неделями
const LABEL_W = 210;
const ROW_H = 26;

// Штриховка отпуска (синеватая) и праздника (тусклая серая).
const ABSENCE_FILL =
  'repeating-linear-gradient(45deg, rgba(116,150,224,0.7) 0 3px, rgba(116,150,224,0.22) 3px 6px)';
const HOLIDAY_FILL =
  'repeating-linear-gradient(45deg, rgba(255,255,255,0.16) 0 3px, rgba(255,255,255,0.04) 3px 6px)';

function isoDate(s: string): Date {
  return new Date(s + 'T00:00:00');
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

type Off = 'weekend' | 'holiday' | 'absence' | null | undefined;

interface Day {
  date: string;
  dow: number; // 0=Вс
}

interface Week {
  days: Day[];
  monthLabel: string | null;
}

export default function EmployeeLoadHeatmap({ rows }: Props) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);

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

    const empRows = rows.map((r) => {
      const byDate = new Map(r.days.map((d) => [d.date, d] as const));
      const workPcts: number[] = [];
      for (const ds of dates) {
        const d = byDate.get(ds);
        if (d && !d.off && d.pct > 0) workPcts.push(d.pct);
      }
      const avg = workPcts.length ? Math.round(workPcts.reduce((s, p) => s + p, 0) / workPcts.length) : 0;
      const allEmpty = dates.every((ds) => {
        const d = byDate.get(ds);
        return !d || d.off || d.pct <= 0;
      });
      return { row: r, byDate, avg, allEmpty };
    });

    const first = isoDate(dates[0]);
    const last = isoDate(dates[dates.length - 1]);
    const periodLabel = `${first.getDate()} ${RU_MONTHS_SHORT[first.getMonth()]} – ${last.getDate()} ${RU_MONTHS_SHORT[last.getMonth()]}`;
    return { weeks, empRows, periodLabel };
  }, [rows]);

  if (!data) return null;

  const showTip = (e: React.MouseEvent, date: string, off: Off, pct: number) => {
    const dt = isoDate(date);
    const head = `${RU_WD[dt.getDay()]}, ${dt.getDate()} ${RU_MONTHS_SHORT[dt.getMonth()]}`;
    let body: string;
    if (off === 'absence') body = 'отпуск / отсутствие';
    else if (off === 'holiday') body = 'праздник';
    else body = pct > 0 ? `${Math.round(pct)}%` : 'нет загрузки';
    setTip({ x: e.clientX, y: e.clientY, text: `${head} · ${body}` });
  };

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
        <div style={{ fontSize: 11, color: 'var(--text-muted, #7a9ab8)' }}>{data.periodLabel}</div>
      </div>
      <div style={{ fontSize: 11, color: '#5a7a9a', marginBottom: 8 }}>
        Только рабочие дни. Наведите на день, чтобы увидеть дату и загрузку.
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

          {/* Строки сотрудников */}
          {data.empRows.map(({ row, byDate, avg, allEmpty }, ri) => {
            const avgColor = loadColor(avg);
            return (
              <div
                key={row.employee_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  height: ROW_H,
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
                  <span
                    style={{
                      fontSize: 12,
                      color: '#fff',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {row.employee_name ?? row.employee_id}
                  </span>
                  {row.employee_role && (
                    <span style={{ fontSize: 10, color: '#5a8ab8', flexShrink: 0 }}>{row.employee_role}</span>
                  )}
                  {avg > 0 && (
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
                  )}
                </div>

                {/* Клетки дней или подпись «нет загрузки» */}
                {allEmpty ? (
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
                        let bg: string;
                        let border: string | undefined;
                        if (off === 'absence') bg = ABSENCE_FILL;
                        else if (off === 'holiday') bg = HOLIDAY_FILL;
                        else {
                          const c = loadColor(pct);
                          bg = c.bg;
                          border = c.border;
                        }
                        return (
                          <div
                            key={cell.date}
                            onMouseEnter={(e) => showTip(e, cell.date, off, pct)}
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
              </div>
            );
          })}
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
            left: tip.x + 12,
            top: tip.y + 14,
            zIndex: 1000,
            pointerEvents: 'none',
            background: '#0a1628',
            border: '1px solid #1e3a5f',
            borderRadius: 6,
            padding: '4px 8px',
            fontSize: 11,
            color: '#e6f0fa',
            whiteSpace: 'nowrap',
            boxShadow: '0 4px 14px rgba(0,0,0,0.45)',
          }}
        >
          {tip.text}
        </div>
      )}
    </div>
  );
}
