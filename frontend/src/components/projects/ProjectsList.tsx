import React from 'react';
import { Skeleton, Empty, Select, Tag, Button } from 'antd';
import { useProjectsList } from '../../hooks/useProjects';
import type { ProjectListFiltersState } from '../../types/projects';
import { ProjectListCard } from './ProjectListCard';
import { ProjectListFilters } from './ProjectListFilters';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  selectedKey: string | null;
  onSelect: (key: string) => void;
  filters: ProjectListFiltersState;
  onFiltersChange: (next: ProjectListFiltersState) => void;
  onShowPortfolio: () => void;
}

const CURRENT_YEAR = new Date().getFullYear();

export const ProjectsList: React.FC<Props> = ({
  selectedKey, onSelect, filters, onFiltersChange, onShowPortfolio,
}) => {
  const patch = (part: Partial<ProjectListFiltersState>) =>
    onFiltersChange({ ...filters, ...part });

  const { data: projects, isLoading } = useProjectsList({
    search: filters.search || undefined,
    status_category: filters.statusCategory || undefined,
    category: filters.category || undefined,
    year: filters.year,
    quarter: filters.quarter,
  });

  const yearOptions = Array.from({ length: 5 }, (_, i) => {
    const y = CURRENT_YEAR - 1 + i;
    return { value: y, label: String(y) };
  });

  return (
    <div
      style={{
        width: 360,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        borderRight: `1px solid ${DARK_THEME.border}`,
        background: DARK_THEME.cardBg,
        height: '100%',
      }}
    >
      <div style={{ padding: '12px 12px 8px', borderBottom: `1px solid ${DARK_THEME.border}` }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 8,
        }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: DARK_THEME.textPrimary }}>
            Проекты
            {projects && (
              <span style={{ fontSize: 12, fontWeight: 400, color: DARK_THEME.textMuted, marginLeft: 8 }}>
                {projects.length}
              </span>
            )}
          </div>
          <Button
            size="small"
            type={selectedKey ? 'default' : 'primary'}
            onClick={onShowPortfolio}
          >
            Сводка
          </Button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <Select
            value={filters.year}
            onChange={(y) => patch({ year: y })}
            options={yearOptions}
            style={{ width: 78 }}
            size="small"
          />
          {([1, 2, 3, 4] as const).map((q) => (
            <Tag
              key={q}
              color={filters.quarter === q ? 'cyan' : undefined}
              style={{ cursor: 'pointer', userSelect: 'none', marginRight: 0, fontSize: 12 }}
              onClick={() => patch({ quarter: q })}
            >
              Q{q}
            </Tag>
          ))}
        </div>
      </div>

      <ProjectListFilters
        search={filters.search}
        onSearchChange={(v) => patch({ search: v })}
        statusCategory={filters.statusCategory}
        onStatusCategoryChange={(v) => patch({ statusCategory: v })}
        category={filters.category}
        onCategoryChange={(v) => patch({ category: v })}
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
