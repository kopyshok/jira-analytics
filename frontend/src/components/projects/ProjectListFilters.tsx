import React, { useEffect, useState } from 'react';
import { Input, Radio, Segmented, Select } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  search: string;
  onSearchChange: (v: string) => void;
  statusCategory: string;
  onStatusCategoryChange: (v: string) => void;
  category: string;
  onCategoryChange: (v: string) => void;
  /** bar — под шапкой списка (Aurora); stack — столбиком в паспорте экрана вместе с годом и кварталом (обложки). */
  variant?: 'bar' | 'stack';
  /** Год и квартал — только для раскладки stack (в Aurora они в шапке списка). */
  year?: number;
  quarter?: number;
  yearOptions?: { value: number; label: string }[];
  onYearChange?: (y: number) => void;
  onQuarterChange?: (q: number) => void;
}

const STATUS_OPTIONS = [
  { value: '', label: 'Все' },
  { value: 'indeterminate', label: 'В работе' },
  { value: 'done', label: 'Готов' },
];
const CATEGORY_OPTIONS = [
  { value: '', label: 'Все' },
  { value: 'quarterly_tasks', label: 'Квартальные' },
  { value: 'archive_target', label: 'Архив' },
];

export const ProjectListFilters: React.FC<Props> = ({
  search,
  onSearchChange,
  statusCategory,
  onStatusCategoryChange,
  category,
  onCategoryChange,
  variant = 'bar',
  year,
  quarter,
  yearOptions,
  onYearChange,
  onQuarterChange,
}) => {
  const [localSearch, setLocalSearch] = useState(search);

  useEffect(() => {
    setLocalSearch(search);
  }, [search]);

  useEffect(() => {
    const timer = setTimeout(() => {
      onSearchChange(localSearch);
    }, 300);
    return () => clearTimeout(timer);
  }, [localSearch, onSearchChange]);

  if (variant === 'stack') {
    return (
      <div className="pj-filters-stack">
        <div className="pj-filters-period">
          <div className="sw-field">
            <div className="sw-field-label">Год</div>
            <Select
              variant="underlined"
              value={year}
              onChange={(y) => onYearChange?.(y)}
              options={yearOptions}
            />
          </div>
          <div className="sw-field">
            <div className="sw-field-label">Квартал</div>
            <Segmented
              block
              value={quarter}
              onChange={(q) => onQuarterChange?.(Number(q))}
              options={[1, 2, 3, 4].map((q) => ({ value: q, label: `Q${q}` }))}
            />
          </div>
        </div>
        <div className="sw-field">
          <div className="sw-field-label">Поиск</div>
          <Input
            variant="underlined"
            placeholder="Поиск по названию или ключу"
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            allowClear
          />
        </div>
        <div className="sw-field">
          <div className="sw-field-label">Статус</div>
          <Segmented block value={statusCategory} onChange={(v) => onStatusCategoryChange(String(v))} options={STATUS_OPTIONS} />
        </div>
        <div className="sw-field">
          <div className="sw-field-label">Категория</div>
          <Segmented block value={category} onChange={(v) => onCategoryChange(String(v))} options={CATEGORY_OPTIONS} />
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '12px 12px 8px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <Input
        prefix={<SearchOutlined style={{ color: DARK_THEME.textMuted }} />}
        placeholder="Поиск по названию или ключу"
        value={localSearch}
        onChange={(e) => setLocalSearch(e.target.value)}
        allowClear
        size="small"
        style={{ background: DARK_THEME.pageBg, borderColor: DARK_THEME.border }}
      />
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <Radio.Group
          size="small"
          value={statusCategory}
          onChange={(e) => onStatusCategoryChange(e.target.value)}
          optionType="button"
          buttonStyle="solid"
        >
          <Radio.Button value="">Все</Radio.Button>
          <Radio.Button value="indeterminate">В работе</Radio.Button>
          <Radio.Button value="done">Готов</Radio.Button>
        </Radio.Group>
        <Radio.Group
          size="small"
          value={category}
          onChange={(e) => onCategoryChange(e.target.value)}
          optionType="button"
          buttonStyle="solid"
        >
          <Radio.Button value="">Все</Radio.Button>
          <Radio.Button value="quarterly_tasks">Квартальные</Radio.Button>
          <Radio.Button value="archive_target">Архив</Radio.Button>
        </Radio.Group>
      </div>
    </div>
  );
};
