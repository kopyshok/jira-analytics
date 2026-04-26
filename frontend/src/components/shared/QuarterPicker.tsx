import { Select, Space, Tag } from 'antd';
import type { QuarterPeriod } from '../../types/api';

const QUARTER_MONTHS: Record<number, { num: number; label: string }[]> = {
  1: [{ num: 1, label: 'Янв' }, { num: 2, label: 'Фев' }, { num: 3, label: 'Мар' }],
  2: [{ num: 4, label: 'Апр' }, { num: 5, label: 'Май' }, { num: 6, label: 'Июн' }],
  3: [{ num: 7, label: 'Июл' }, { num: 8, label: 'Авг' }, { num: 9, label: 'Сен' }],
  4: [{ num: 10, label: 'Окт' }, { num: 11, label: 'Ноя' }, { num: 12, label: 'Дек' }],
};

interface Props {
  value: QuarterPeriod;
  onChange: (p: QuarterPeriod) => void;
}

export default function QuarterPicker({ value, onChange }: Props) {
  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 5 }, (_, i) => {
    const y = currentYear - 1 + i;
    return { value: y, label: String(y) };
  });

  const handleMonth = (month: number) => {
    if (value.month === month) {
      onChange({ ...value, month: undefined });
    } else {
      onChange({ ...value, month });
    }
  };

  return (
    <Space size={4} wrap>
      <Select
        value={value.year}
        onChange={(y) => onChange({ ...value, year: y, month: undefined })}
        options={yearOptions}
        style={{ width: 84 }}
        size="small"
      />
      {([1, 2, 3, 4] as const).map((q) => (
        <Tag
          key={q}
          color={value.quarter === q ? 'cyan' : undefined}
          style={{ cursor: 'pointer', userSelect: 'none', marginRight: 0 }}
          onClick={() => onChange({ ...value, quarter: q, month: undefined })}
        >
          Q{q}
        </Tag>
      ))}
      {QUARTER_MONTHS[value.quarter].map(({ num, label }) => (
        <Tag
          key={num}
          color={value.month === num ? 'blue' : undefined}
          style={{ cursor: 'pointer', userSelect: 'none', fontSize: 11, marginRight: 0 }}
          onClick={() => handleMonth(num)}
        >
          {label}
        </Tag>
      ))}
    </Space>
  );
}
