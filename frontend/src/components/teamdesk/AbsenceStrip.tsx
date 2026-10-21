import { Empty, Select, Space, Typography } from 'antd';
import { useState } from 'react';
import AbsenceHeatmap from '../capacity/AbsenceHeatmap';
import { useAbsences } from '../../hooks/useAbsences';
import { useEmployees } from '../../hooks/useCapacity';

const QUARTERS = [1, 2, 3, 4];

interface Props {
  /** id сотрудников, попавших в срез стола (ключ — учётная запись Jira) */
  employeeIds: Record<string, string>;
  /** Узкая колонка (скин «Цветовые зоны»): период одним списком, клетка — неделя. */
  compact?: boolean;
  /** Период задаёт владелец (подпись над списком считает тот же квартал); без него — свой. */
  period?: { year: number; quarter: number };
  onPeriodChange?: (period: { year: number; quarter: number }) => void;
}

/** Отсутствия людей стола: переиспользуем теплокарту с экрана ёмкости. */
export function AbsenceStrip({ employeeIds, compact = false, period, onPeriodChange }: Props) {
  const now = new Date();
  const [ownYear, setOwnYear] = useState(now.getFullYear());
  const [ownQuarter, setOwnQuarter] = useState(Math.floor(now.getMonth() / 3) + 1);
  const year = period?.year ?? ownYear;
  const quarter = period?.quarter ?? ownQuarter;
  const setYear = (y: number) => (onPeriodChange ? onPeriodChange({ year: y, quarter }) : setOwnYear(y));
  const setQuarter = (q: number) => (onPeriodChange ? onPeriodChange({ year, quarter: q }) : setOwnQuarter(q));

  const absences = useAbsences();
  const employees = useEmployees();

  const wanted = new Set(Object.values(employeeIds));
  const rows = (employees.data ?? [])
    .filter((e) => wanted.has(e.id))
    .map((e) => ({ id: e.id, display_name: e.display_name }));

  if (!rows.length) {
    return <Empty description="Выберите команды или людей" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  if (compact) {
    const years = [now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1];
    return (
      <div className="absence-strip-compact">
        <label className="absence-strip-period">
          Период
          <Select
            size="small"
            value={`${year}-${quarter}`}
            onChange={(v: string) => {
              const [y, q] = v.split('-').map(Number);
              if (onPeriodChange) onPeriodChange({ year: y, quarter: q });
              else { setOwnYear(y); setOwnQuarter(q); }
            }}
            options={years.flatMap((y) => QUARTERS.map((q) => ({ value: `${y}-${q}`, label: `${y} · Q${q}` })))}
            style={{ width: 110 }}
            popupMatchSelectWidth={false}
          />
        </label>
        <AbsenceHeatmap
          compact
          year={year}
          quarter={quarter}
          employees={rows}
          absences={absences.data ?? []}
        />
      </div>
    );
  }

  return (
    <Space orientation="vertical" size={10} style={{ width: '100%' }}>
      <Space size={8}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>Период</Typography.Text>
        <Select
          size="small"
          value={year}
          onChange={setYear}
          options={[year - 1, year, year + 1].map((y) => ({ value: y, label: String(y) }))}
          style={{ width: 90 }}
        />
        <Select
          size="small"
          value={quarter}
          onChange={setQuarter}
          options={QUARTERS.map((q) => ({ value: q, label: `Q${q}` }))}
          style={{ width: 80 }}
        />
      </Space>
      <div style={{ overflowX: 'auto' }}>
        <AbsenceHeatmap
          year={year}
          quarter={quarter}
          employees={rows}
          absences={absences.data ?? []}
        />
      </div>
    </Space>
  );
}
