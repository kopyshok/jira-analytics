import React from 'react';
import { Card, Empty, Skeleton } from 'antd';
import { useIsFetching } from '@tanstack/react-query';
import type { ProjectSummary } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

interface Props {
  summary: ProjectSummary | null | undefined;
  description: string | null;
}

const GOAL_COLORS = ['#378ADD', '#1D9E75', '#EF9F27'];

export const ProjectGoalsCard: React.FC<Props> = ({ summary, description }) => {
  const isFetchingSummary = useIsFetching({ queryKey: ['project-summary'] }) > 0;
  const goals = summary?.goals;

  const renderContent = () => {
    if (!summary && isFetchingSummary) {
      return <Skeleton active paragraph={{ rows: 3 }} title={false} />;
    }
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
                  color: DARK_THEME.textPrimary,
                  flexShrink: 0,
                  marginTop: 1,
                }}
              >
                {i + 1}
              </div>
              <span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13, lineHeight: 1.5 }}>{goal}</span>
            </li>
          ))}
        </ol>
      );
    }
    if (description) {
      return (
        <p style={{ margin: 0, color: DARK_THEME.textMuted, fontSize: 13, lineHeight: 1.6 }}>
          {description.slice(0, 600)}
        </p>
      );
    }
    return <Empty description="AI-цели генерируются" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  };

  return (
    <Card
      size="small"
      title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Цели проекта</span>}
      style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      {renderContent()}
    </Card>
  );
};
