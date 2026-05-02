import React, { useEffect, useState } from 'react';
import { Input, Radio } from 'antd';
import { SearchOutlined } from '@ant-design/icons';

interface Props {
  search: string;
  onSearchChange: (v: string) => void;
  statusCategory: string;
  onStatusCategoryChange: (v: string) => void;
  category: string;
  onCategoryChange: (v: string) => void;
}

export const ProjectListFilters: React.FC<Props> = ({
  search,
  onSearchChange,
  statusCategory,
  onStatusCategoryChange,
  category,
  onCategoryChange,
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

  return (
    <div style={{ padding: '12px 12px 8px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <Input
        prefix={<SearchOutlined style={{ color: '#7e94b8' }} />}
        placeholder="Поиск по названию или ключу"
        value={localSearch}
        onChange={(e) => setLocalSearch(e.target.value)}
        allowClear
        size="small"
        style={{ background: '#0d1c33', borderColor: '#1e3356' }}
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
