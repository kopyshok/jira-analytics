import React, { useEffect, useState } from 'react';
import { Input, Radio, Segmented } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { Search } from 'lucide-react';
import { DARK_THEME } from '../../utils/constants';

/** Значение «Все» в сегментах скина: пустая строка для переключателя не годится. */
const ALL = 'all';

interface Props {
  search: string;
  onSearchChange: (v: string) => void;
  statusCategory: string;
  onStatusCategoryChange: (v: string) => void;
  category: string;
  onCategoryChange: (v: string) => void;
  /** Вид скина: поле поиска во всю ширину и сегменты-пилюли (классы pjc-*). */
  compact?: boolean;
}

export const ProjectListFilters: React.FC<Props> = ({
  search,
  onSearchChange,
  statusCategory,
  onStatusCategoryChange,
  category,
  onCategoryChange,
  compact = false,
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

  if (compact) {
    return (
      <div className="pjc-filters">
        <Input
          className="pjc-search"
          prefix={<Search size={16} aria-hidden />}
          placeholder="Поиск по названию или ключу"
          aria-label="Поиск по названию или ключу"
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
          allowClear
        />
        <Segmented
          block
          aria-label="Статус"
          value={statusCategory || ALL}
          onChange={(v) => onStatusCategoryChange(v === ALL ? '' : String(v))}
          options={[
            { value: ALL, label: 'Все' },
            { value: 'indeterminate', label: 'В работе' },
            { value: 'done', label: 'Готов' },
          ]}
        />
        <Segmented
          block
          aria-label="Категория"
          value={category || ALL}
          onChange={(v) => onCategoryChange(v === ALL ? '' : String(v))}
          options={[
            { value: ALL, label: 'Все' },
            { value: 'quarterly_tasks', label: 'Квартальные' },
            { value: 'archive_target', label: 'Архив' },
          ]}
        />
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
