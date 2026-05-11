import React, { useState } from 'react';
import { Skeleton, Empty, Select, Tag } from 'antd';
import { useProjectsList } from '../../hooks/useProjects';
import { ProjectListCard } from './ProjectListCard';
import { ProjectListFilters } from './ProjectListFilters';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_QUARTER = Math.floor(new Date().getMonth() / 3) + 1 as 1 | 2 | 3 | 4;

export const ProjectsList: React.FC<Props> = ({ selectedKey, onSelect }) => {
  const [search, setSearch] = useState('');
  const [statusCategory, setStatusCategory] = useState('');
  const [category, setCategory] = useState('');
  const [year, setYear] = useState<number>(CURRENT_YEAR);
  const [quarter, setQuarter] = useState<number>(CURRENT_QUARTER);

  const { data: projects, isLoading } = useProjectsList({
    search: search || undefined,
    status_category: statusCategory || undefined,
    category: category || undefined,
    year,
    quarter,
  });

  const yearOptions = Array.from({ length: 5 }, (_, i) => {
    const y = CURRENT_YEAR - 1 + i;
    return { value: y, label: String(y) };
  });

  return (
    <div
      style={{
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: DARK_THEME.cardBg,
        minHeight: '100%',
      }}
    >
      <div
        style={{
          padding: '12px 12px 8px',
          borderBottom: `1px solid ${DARK_THEME.border}`,
        }}
      >
        <div style={{ fontSize: 15, fontWeight: 700, color: DARK_THEME.textPrimary, marginBottom: 8 }}>
          Проекты
          {projects && (
            <span style={{ fontSize: 12, fontWeight: 400, color: DARK_THEME.textMuted, marginLeft: 8 }}>
              {projects.length}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <Select
            value={year}
            onChange={(y) => setYear(y)}
            options={yearOptions}
            style={{ width: 78 }}
            size="small"
          />
          {([1, 2, 3, 4] as const).map((q) => (
            <Tag
              key={q}
              color={quarter === q ? 'cyan' : undefined}
              style={{ cursor: 'pointer', userSelect: 'none', marginRight: 0, fontSize: 12 }}
              onClick={() => setQuarter(q)}
            >
              Q{q}
            </Tag>
          ))}
        </div>
      </div>

      <ProjectListFilters
        search={search}
        onSearchChange={setSearch}
        statusCategory={statusCategory}
        onStatusCategoryChange={setStatusCategory}
        category={category}
        onCategoryChange={setCategory}
      />

      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px 8px' }}>
        {isLoading && (
          <>
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} active paragraph={{ rows: 2 }} style={{ marginBottom: 8 }} />
            ))}
          </>
        )}
        {!isLoading && (!projects || projects.length === 0) && (
          <Empty
            description="Нет проектов"
            style={{ marginTop: 48, color: DARK_THEME.textMuted }}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )}
        {!isLoading &&
          projects?.map((item) => (
            <ProjectListCard
              key={item.key}
              item={item}
              selected={item.key === selectedKey}
              onClick={() => onSelect(item.key)}
            />
          ))}
      </div>
    </div>
  );
};
