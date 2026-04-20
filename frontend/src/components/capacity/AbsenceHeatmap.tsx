import { Tooltip } from 'antd';
import dayjs from 'dayjs';
import type { AbsenceResponse, AbsenceReason } from '../../types/api';

const REASON_COLOR: Record<AbsenceReason, string> = {
  vacation: '#fa8c16',
  sick:     '#f5222d',
  day_off:  '#1677ff',
  other:    '#8c8c8c',
};
const REASON_LABEL: Record<AbsenceReason, string> = {
  vacation: 'Отпуск', sick: 'Больничный', day_off: 'Отгул', other: 'Прочее',
};

const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12],
};

interface Props {
  year: number;
  quarter: number;
  employees: Array<{ id: string; display_name: string }>;
  absences: AbsenceResponse[];
}

export default function AbsenceHeatmap({ year, quarter, employees, absences }: Props) {
  const months = QUARTER_MONTHS[quarter] ?? [];
  if (months.length === 0) return null;

  const start = dayjs(`${year}-${String(months[0]).padStart(2, '0')}-01`);
  const end = dayjs(`${year}-${String(months[months.length - 1]).padStart(2, '0')}-01`).endOf('month');
  const days: dayjs.Dayjs[] = [];
  for (let d = start; d.isBefore(end) || d.isSame(end, 'day'); d = d.add(1, 'day')) {
    days.push(d);
  }

  const byEmployee = new Map<string, AbsenceResponse[]>();
  for (const a of absences) {
    const arr = byEmployee.get(a.employee_id) ?? [];
    arr.push(a);
    byEmployee.set(a.employee_id, arr);
  }

  const reasonForDay = (list: AbsenceResponse[] | undefined, d: dayjs.Dayjs): AbsenceResponse | null => {
    if (!list) return null;
    for (const a of list) {
      if (d.isBefore(dayjs(a.start_date))) continue;
      if (d.isAfter(dayjs(a.end_date))) continue;
      return a;
    }
    return null;
  };

  const cell = 18;
  return (
    <div style={{ overflowX: 'auto', marginBottom: 12 }}>
      <div style={{ display: 'inline-grid', gridTemplateColumns: `180px repeat(${days.length}, ${cell}px)`, gap: 1 }}>
        <div />
        {days.map((d) => (
          <div key={`h-${d.format('YYYY-MM-DD')}`}
               style={{ fontSize: 9, textAlign: 'center',
                        color: d.day() === 0 || d.day() === 6 ? '#6b7a94' : '#c0c8d4' }}>
            {d.date() === 1 || d.date() % 5 === 0 ? d.date() : ''}
          </div>
        ))}
        {employees.map((e) => {
          const list = byEmployee.get(e.id);
          return (
            <div key={`row-${e.id}`} style={{ display: 'contents' }}>
              <div style={{ fontSize: 12, paddingRight: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {e.display_name}
              </div>
              {days.map((d) => {
                const a = reasonForDay(list, d);
                const weekend = d.day() === 0 || d.day() === 6;
                const bg = a
                  ? REASON_COLOR[a.reason]
                  : (weekend ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.06)');
                const tip = a
                  ? `${e.display_name}: ${REASON_LABEL[a.reason]}, ${dayjs(a.start_date).format('DD.MM')}–${dayjs(a.end_date).format('DD.MM')}`
                  : `${e.display_name} · ${d.format('DD.MM')}`;
                return (
                  <Tooltip key={`${e.id}-${d.format('YYYY-MM-DD')}`} title={tip} mouseEnterDelay={0.3}>
                    <div style={{ height: 18, background: bg, borderRadius: 2 }} />
                  </Tooltip>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
