import React from 'react';
import { Card, Empty } from 'antd';
import { useNavigate } from 'react-router';
import type { CategoryBreakdown } from '../../../types/projects';

interface Props {
  categories: CategoryBreakdown[];
  projectKey: string;
}

const DEFAULT_COLOR = '#7e94b8';

export const ProjectKeyBlocksCard: React.FC<Props> = ({ categories, projectKey }) => {
  const navigate = useNavigate();

  const top3 = [...(categories ?? [])].sort((a, b) => b.hours - a.hours).slice(0, 3);
  const maxHours = top3[0]?.hours ?? 1;

  return (
    <Card
      size="small"
      title={<span style={{ color: '#cfd8e5', fontSize: 13 }}>Ключевые блоки работ</span>}
      style={{ background: '#0f2340', border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      {top3.length === 0 ? (
        <Empty description="Нет данных" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {top3.map((c) => (
            <div
              key={c.code}
              style={{ cursor: 'pointer' }}
              onClick={() => navigate(`/analytics?category=${c.code}&project=${projectKey}`)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ color: '#cfd8e5', fontSize: 12 }}>{c.label}</span>
                <span style={{ color: '#7e94b8', fontSize: 11 }}>{c.hours} ч</span>
              </div>
              <div style={{ height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${(c.hours / maxHours) * 100}%`,
                    background: c.color ?? DEFAULT_COLOR,
                    borderRadius: 3,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};
