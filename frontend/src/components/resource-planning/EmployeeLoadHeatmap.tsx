import { useMemo, useState } from 'react';

import type { EmployeeLoadOut } from '../../api/resourcePlanning';

interface Props {
  rows: EmployeeLoadOut[];
}

const RU_MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const RU_WD = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

const CELL = 15; // ширина/высота клетки дня
const CELL_GAP = 2; // зазор между днями внутри недели
const WEEK_GAP = 6; // зазор между неделями
const LABEL_W = 210;
const ROW_H = 26;

function isoDate(s: string): Date {
  return new Date(s + 'T00:00:00');
}

/** Цвет клетки по загрузке. Тинтуем нейтрали к навигационному оттенку, без чистых тонов. */
function loadColor(pct: number): { bg: string; border?: string } {
  if (pct <= 0) {
    // «Отдыхающая» клетка: выходной или нулевой день. Не дыра, но и не цвет.
    return { bg: 'rgba(255,255,255,0.035)', border: '1px solid rgba(255,255,255,0.05)' };
  }
  if (pct > 110) {
    // Перегруз: янтарь → красный.
    const t = Math.min((pct - 110) / 40, 1);
    const h = 38 - 36 * t;
    return { bg: `hsl(${h} 82% 52%)` };
  }
  // 1..110 — приглушённо-зелёный → насыщенный зелёный.
  const t = Math.min(pct, 110) / 110;
  const light = 24 + 26 * t;
  const sat = 28 + 46 * t;
  return { bg: `hsl(150 ${sat}% ${light}%)` };
}

interface Day {
  date: string;
  pct: number;
  dow: number; // 0=Вс
}

interface Week {
  days: Day[];
  monthLabel: string | null; // непустой на первой неделе месяца
}

export default function EmployeeLoadHeatmap({ rows }: Props) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);

  const data = useMemo(() => {
    if (rows.length === 0) return null;
    // Ось дней — объединение всех дат, по возрастанию.
    const dateSet = new Set<string>();
    for (const r of rows) for (const d of r.days) dateSet.add(d.date);
    const dates = Array.from(dateSet).sort();
    if (dates.length === 0) return null;

    // Разбиваем дни на недели (Пн–Вс) для зазоров и шапки-месяцев.
    const weeks: Week[] = [];
    let seenMonth = -1;
    for (const ds of dates) {
      const dt = isoDate(ds);
      const dow = dt.getDay();
      const isMonday = dow === 1;
      if (weeks.length === 0 || isMonday) {
        const m = dt.getMonth();
        const monthLabel = m !== seenMonth ? RU_MONTHS_SHORT[m].toUpperCase() : null;
        if (m !== seenMonth) seenMonth = m;
        weeks.push({ days: [], monthLabel });
      }
      // Месяц мог смениться в середине недели — пометим первую неделю месяца.
      const m = dt.getMonth();
      if (m !== seenMonth && weeks[weeks.length - 1].monthLabel === null) {
        weeks[weeks.length - 1].monthLabel = RU_MONTHS_SHORT[m].toUpperCase();
        seenMonth = m;
      }
      weeks[weeks.length - 1].days.push({ date: ds, pct: 0, dow });
    }

    // Загрузка по сотруднику: date -> pct + средняя по будням.
    const empRows = rows.map((r) => {
      const byDate = new Map(r.days.map((d) => [d.date, d.pct] as const));
      const empWeeks: Week[] = weeks.map((w) => ({
        monthLabel: w.monthLabel,
        days: w.days.map((d) => ({ ...d, pct: byDate.get(d.date) ?? 0 })),
      }));
      // Средняя только по будням с ненулевой загрузкой.
      const workdayPcts: number[] = [];
      for (const ds of dates) {
        const dow = isoDate(ds).getDay();
        if (dow >= 1 && dow <= 5) {
          const p = byDate.get(ds) ?? 0;
          if (p > 0) workdayPcts.push(p);
        }
      }
      const avg = workdayPcts.length
        ? Math.round(workdayPcts.reduce((s, p) => s + p, 0) / workdayPcts.length)
        : 0;
      return { row: r, weeks: empWeeks, avg };
    });

    const first = isoDate(dates[0]);
    const last = isoDate(dates[dates.length - 1]);
    const periodLabel = `${first.getDate()} ${RU_MONTHS_SHORT[first.getMonth()]} – ${last.getDate()} ${RU_MONTHS_SHORT[last.getMonth()]}`;
    return { weeks, empRows, periodLabel };
  }, [rows]);

  if (!data) return null;

  const onCellEnter = (e: React.MouseEvent, d: Day) => {
    const dt = isoDate(d.date);
    const head = `${RU_WD[d.dow]}, ${dt.getDate()} ${RU_MONTHS_SHORT[dt.getMonth()]}`;
    const body = d.pct > 0 ? `${Math.round(d.pct)}%` : d.dow === 0 || d.dow === 6 ? 'выходной' : 'нет загрузки';
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
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 4,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Загрузка сотрудников по дням</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted, #7a9ab8)' }}>{data.periodLabel}</div>
      </div>
      <div style={{ fontSize: 11, color: '#5a7a9a', marginBottom: 8 }}>
        Наведите на день, чтобы увидеть дату и загрузку.
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
              <div
                key={wi}
                style={{
                  display: 'flex',
                  marginLeft: wi === 0 ? 0 : WEEK_GAP,
                  position: 'relative',
                }}
              >
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
          {data.empRows.map(({ row, weeks, avg }, ri) => {
            const allEmpty = weeks.every((w) => w.days.every((d) => d.pct <= 0));
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
                  weeks.map((w, wi) => (
                    <div key={wi} style={{ display: 'flex', marginLeft: wi === 0 ? 0 : WEEK_GAP }}>
                      {w.days.map((d) => {
                        const c = loadColor(d.pct);
                        return (
                          <div
                            key={d.date}
                            onMouseEnter={(e) => onCellEnter(e, d)}
                            onMouseLeave={() => setTip(null)}
                            style={{
                              width: CELL,
                              height: CELL,
                              marginRight: CELL_GAP,
                              borderRadius: 3,
                              background: c.bg,
                              border: c.border,
                              cursor: 'default',
                              transition: 'filter 160ms cubic-bezier(0.22,1,0.36,1)',
                            }}
                            onMouseOver={(e) => {
                              (e.currentTarget as HTMLDivElement).style.filter = 'brightness(1.25)';
                            }}
                            onMouseOut={(e) => {
                              (e.currentTarget as HTMLDivElement).style.filter = 'none';
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
          { label: 'выходной', pct: 0 },
          { label: 'до 60%', pct: 45 },
          { label: '60–90%', pct: 80 },
          { label: '90–110%', pct: 100 },
          { label: 'свыше 110%', pct: 125 },
        ].map((it) => {
          const c = loadColor(it.pct);
          return (
            <span key={it.label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#9ab3cc' }}>
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 3,
                  background: c.bg,
                  border: c.border,
                  display: 'inline-block',
                }}
              />
              {it.label}
            </span>
          );
        })}
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
