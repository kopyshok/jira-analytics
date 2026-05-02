import React, { useState } from 'react';
import { Skeleton, Empty } from 'antd';
import { useProjectsList } from '../../hooks/useProjects';
import { ProjectListCard } from './ProjectListCard';
import { ProjectListFilters } from './ProjectListFilters';

interface Props {
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

export const ProjectsList: React.FC<Props> = ({ selectedKey, onSelect }) => {
  const [search, setSearch] = useState('');
  const [statusCategory, setStatusCategory] = useState('');
  const [category, setCategory] = useState('');

  const { data: projects, isLoading } = useProjectsList({
    search: search || undefined,
    status_category: statusCategory || undefined,
    category: category || undefined,
  });

  return (
    <div
      style={{
        width: 360,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        borderRight: '1px solid #1e3356',
        background: '#0f2340',
        height: '100%',
      }}
    >
      <div
        style={{
          padding: '16px 12px 4px',
          borderBottom: '1px solid #1e3356',
          fontSize: 15,
          fontWeight: 700,
          color: '#e8f0fa',
        }}
      >
        Проекты
        {projects && (
          <span style={{ fontSize: 12, fontWeight: 400, color: '#7e94b8', marginLeft: 8 }}>
            {projects.length}
          </span>
        )}
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
            style={{ marginTop: 48, color: '#7e94b8' }}
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
