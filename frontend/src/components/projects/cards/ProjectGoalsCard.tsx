import React from 'react';
import { Card, Empty } from 'antd';
import type { ProjectSummary } from '../../../types/projects';

interface Props {
  summary: ProjectSummary | null | undefined;
  description: string | null;
}

const GOAL_COLORS = ['#378ADD', '#1D9E75', '#EF9F27'];

export const ProjectGoalsCard: React.FC<Props> = ({ summary, description }) => {
  const goals = summary?.goals;

  const renderContent = () => {
    if (goals && goals.length > 0) {
      return (
        <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {goals.map((goal, i) => (
            <li key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: GOAL_COLORS[i % GOAL_COLORS.length],
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                  color: '#fff',
                  flexShrink: 0,
                  marginTop: 1,
                }}
              >
                {i + 1}
              </div>
              <span style={{ color: '#cfd8e5', fontSize: 13, lineHeight: 1.5 }}>{goal}</span>
            </li>
          ))}
        </ol>
      );
    }
    if (description) {
      return (
        <p style={{ margin: 0, color: '#7e94b8', fontSize: 13, lineHeight: 1.6 }}>
          {description.slice(0, 600)}
        </p>
      );
    }
    return <Empty description="AI-цели генерируются" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  };

  return (
    <Card
      size="small"
      title={<span style={{ color: '#cfd8e5', fontSize: 13 }}>Цели проекта</span>}
      style={{ background: '#0f2340', border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      {renderContent()}
    </Card>
  );
};
