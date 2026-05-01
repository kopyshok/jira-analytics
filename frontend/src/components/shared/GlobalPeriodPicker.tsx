import { Select, Space } from 'antd';
import { useGlobalPeriod } from '../../hooks/useGlobalPeriod';

const QUARTERS = [
  { value: 1, label: 'Q1 (янв-мар)' },
  { value: 2, label: 'Q2 (апр-июн)' },
  { value: 3, label: 'Q3 (июл-сен)' },
  { value: 4, label: 'Q4 (окт-дек)' },
];

const MONTH_NAMES = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12],
};

export default function GlobalPeriodPicker() {
  const { period, setPeriod } = useGlobalPeriod();
  const months = QUARTER_MONTHS[period.quarter] || [];

  return (
    <Space size={4}>
      <Select
        size="small"
        style={{ minWidth: 80 }}
        value={period.year}
        onChange={(v) => setPeriod({ ...period, year: v })}
        options={[period.year - 1, period.year, period.year + 1].map(y => ({ value: y, label: y }))}
      />
      <Select
        size="small"
        style={{ minWidth: 130 }}
        value={period.quarter}
        onChange={(v) => setPeriod({ ...period, quarter: v, month: undefined })}
        options={QUARTERS}
      />
      <Select
        size="small"
        style={{ minWidth: 80 }}
        value={period.month ?? 'all'}
        onChange={(v) => setPeriod({ ...period, month: v === 'all' ? undefined : Number(v) })}
        options={[
          { value: 'all', label: 'Весь Q' },
          ...months.map(m => ({ value: m, label: MONTH_NAMES[m - 1] })),
        ]}
      />
    </Space>
  );
}
