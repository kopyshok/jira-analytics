import React from 'react';
import { Card, Empty } from 'antd';
import { useNavigate } from 'react-router';
import type { CategoryBreakdown } from '../../../types/projects';
import { DonutChart } from '../shared/DonutChart';

interface Props {
  categories: CategoryBreakdown[];
  totalHours: number;
  weeks: number;
  projectKey: string;
}

const DEFAULT_COLOR = '#7e94b8';

export const ProjectCategoriesCard: React.FC<Props> = ({ categories, totalHours, weeks, projectKey }) => {
  const navigate = useNavigate();

  if (!categories || categories.length === 0) {
    return (
      <Card
        size="small"
        title={<span style={{ color: '#cfd8e5', fontSize: 13 }}>Структура трудозатрат</span>}
        style={{ background: '#0f2340', border: '1px solid rgba(255,255,255,0.06)' }}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <Empty description="Нет данных" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const slices = categories.map((c) => ({
    code: c.code,
    label: c.label,
    hours: c.hours,
    color: c.color ?? DEFAULT_COLOR,
  }));

  const handleSliceClick = (slice: { code: string }) => {
    navigate(`/analytics?category=${slice.code}&project=${projectKey}`);
  };

  return (
    <Card
      size="small"
      title={<span style={{ color: '#cfd8e5', fontSize: 13 }}>Структура трудозатрат</span>}
      style={{ background: '#0f2340', border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
        <DonutChart
          slices={slices}
          centerValue={`${totalHours} ч`}
          centerLabel={`~${weeks} нед`}
          size={160}
          onSliceClick={handleSliceClick}
        />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {categories.map((c) => (
            <div
              key={c.code}
              style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
              onClick={() => navigate(`/analytics?category=${c.code}&project=${projectKey}`)}
            >
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: c.color ?? DEFAULT_COLOR,
                  flexShrink: 0,
                }}
              />
              <span style={{ flex: 1, color: '#cfd8e5', fontSize: 12, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {c.label}
              </span>
              <span style={{ color: '#7e94b8', fontSize: 11, whiteSpace: 'nowrap' }}>
                {c.hours} ч · {c.pct}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
};
