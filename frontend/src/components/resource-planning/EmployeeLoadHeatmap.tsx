import { useMemo } from 'react';

import type { EmployeeLoadOut } from '../../api/resourcePlanning';

interface Props {
  rows: EmployeeLoadOut[];
}

const RU_MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

function loadColors(pct: number): { fill: string; bar: string; text: string } {
  if (pct > 110) return { fill: 'rgba(255,77,79,0.18)', bar: 'rgba(255,77,79,0.55)', text: '#ff4d4f' };
  if (pct > 85) return { fill: 'rgba(250,173,20,0.16)', bar: 'rgba(250,173,20,0.45)', text: '#faad14' };
  if (pct > 0) return { fill: 'rgba(82,196,26,0.14)', bar: 'rgba(82,196,26,0.40)', text: '#52c41a' };
  return { fill: 'transparent', bar: 'transparent', text: '#445' };
}

function formatWeekLabel(d: Date): string {
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

function isoDate(s: string): Date {
  return new Date(s + 'T00:00:00');
}

/**
 * Понедельная тепловая карта загрузки сотрудников.
 * Каждый столбец — неделя (Пн–Вс). В ячейке: tint-фон по загрузке +
 * пропорциональная «столбик»-заливка снизу + % число. Маркер «!» для >110%.
 */
export default function EmployeeLoadHeatmap({ rows }: Props) {
  const data = useMemo(() => {
    if (rows.length === 0) return null;
    // Найти границы периода по первой строке.
    const firstDays = rows[0].days;
    if (firstDays.length === 0) return null;
    const start = isoDate(firstDays[0].date);
    const end = isoDate(firstDays[firstDays.length - 1].date);
    // Понедельник недели, в которой лежит start.
    const dow = start.getDay() === 0 ? 6 : start.getDay() - 1;
    const weekStart = new Date(start);
    weekStart.setDate(weekStart.getDate() - dow);
    const weeks: { label: string; start: Date; end: Date }[] = [];
    const cursor = new Date(weekStart);
    while (cursor <= end) {
      const we = new Date(cursor);
      we.setDate(we.getDate() + 6);
      weeks.push({ label: formatWeekLabel(cursor), start: new Date(cursor), end: we });
      cursor.setDate(cursor.getDate() + 7);
    }
    // Для каждой строки — средняя загрузка за неделю.
    const empRows = rows.map((r) => {
      const byWeek: number[] = weeks.map(({ start: ws, end: we }) => {
        const cells = r.days.filter((d) => {
          const dd = isoDate(d.date);
          return dd >= ws && dd <= we && d.pct > 0;
        });
        if (cells.length === 0) return 0;
        return cells.reduce((s, c) => s + c.pct, 0) / cells.length;
      });
      return { row: r, weeks: byWeek };
    });
    return { weeks, empRows, periodLabel: `${start.getDate()} ${RU_MONTHS_SHORT[start.getMonth()]} – ${end.getDate()} ${RU_MONTHS_SHORT[end.getMonth()]}` };
  }, [rows]);

  if (!data) return null;

  const LABEL_W = 200;
  const CELL_W = 56;
  const ROW_H = 28;
  const HEADER_H = 30;
  const totalW = LABEL_W + CELL_W * data.weeks.length;
  const totalH = HEADER_H + ROW_H * data.empRows.length;

  return (
    <div
      style={{
        background: '#0a1628',
        border: '1px solid #1e3a5f',
        borderRadius: 8,
        padding: 12,
        marginTop: 16,
        overflowX: 'auto',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>
          Загрузка сотрудников по неделям
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted, #7a9ab8)' }}>{data.periodLabel}</div>
      </div>
      <svg
        width="100%"
        viewBox={`0 0 ${totalW} ${totalH}`}
        preserveAspectRatio="xMinYMin meet"
        style={{ display: 'block', minWidth: totalW }}
      >
        {/* Header */}
        <rect x={0} y={0} width={totalW} height={HEADER_H} fill="#0d1c33" />
        <text
          x={10}
          y={HEADER_H / 2 + 4}
          fill="#7a9ab8"
          fontSize={10}
          fontWeight={600}
          style={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}
        >
          Сотрудник
        </text>
        {data.weeks.map((w, wi) => (
          <text
            key={wi}
            x={LABEL_W + wi * CELL_W + CELL_W / 2}
            y={HEADER_H / 2 + 4}
            textAnchor="middle"
            fill="#7a9ab8"
            fontSize={10}
            fontFamily="system-ui"
          >
            {w.label}
          </text>
        ))}
        <line x1={0} y1={HEADER_H} x2={totalW} y2={HEADER_H} stroke="#1e3a5f" strokeWidth={1} />

        {/* Rows */}
        {data.empRows.map(({ row, weeks }, ri) => {
          const rowY = HEADER_H + ri * ROW_H;
          const isEven = ri % 2 === 0;
          return (
            <g key={row.employee_id}>
              <rect
                x={0}
                y={rowY}
                width={totalW}
                height={ROW_H}
                fill={isEven ? 'rgba(0,201,200,0.03)' : 'rgba(0,0,0,0.16)'}
              />
              <text
                x={12}
                y={rowY + ROW_H / 2 + 4}
                fill="#fff"
                fontSize={11}
                fontFamily="system-ui"
              >
                {row.employee_name ?? row.employee_id}
              </text>
              {row.employee_role && (
                <text
                  x={LABEL_W - 6}
                  y={rowY + ROW_H / 2 + 4}
                  textAnchor="end"
                  fill="#5a8ab8"
                  fontSize={9}
                  fontFamily="system-ui"
                >
                  {row.employee_role}
                </text>
              )}
              <line
                x1={LABEL_W}
                y1={rowY}
                x2={LABEL_W}
                y2={rowY + ROW_H}
                stroke="#1e3a5f"
                strokeWidth={1}
              />
              {weeks.map((pct, wi) => {
                const cellX = LABEL_W + wi * CELL_W;
                const { fill, bar, text } = loadColors(pct);
                const barH = pct > 0 ? Math.min(pct / 150, 1) * (ROW_H - 10) : 0;
                return (
                  <g key={wi}>
                    <rect
                      x={cellX + 2}
                      y={rowY + 3}
                      width={CELL_W - 4}
                      height={ROW_H - 6}
                      fill={fill}
                      rx={3}
                    />
                    {barH > 0 && (
                      <rect
                        x={cellX + 4}
                        y={rowY + ROW_H - 4 - barH}
                        width={CELL_W - 8}
                        height={barH}
                        fill={bar}
                        rx={2}
                      />
                    )}
                    {pct > 0 && (
                      <text
                        x={cellX + CELL_W / 2}
                        y={rowY + ROW_H / 2 + 4}
                        textAnchor="middle"
                        fill={text}
                        fontSize={10}
                        fontWeight={pct > 100 ? 700 : 400}
                        fontFamily="system-ui"
                      >
                        {Math.round(pct)}%
                      </text>
                    )}
                    {pct > 110 && (
                      <text
                        x={cellX + CELL_W - 4}
                        y={rowY + 11}
                        textAnchor="end"
                        fill="#ff4d4f"
                        fontSize={9}
                        fontWeight={700}
                      >
                        !
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
