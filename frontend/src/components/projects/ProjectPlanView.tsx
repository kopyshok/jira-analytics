import React from 'react';
import { Card, Spin } from 'antd';
import { useProjectPlan } from '../../hooks/useProjects';
import { WorkTypeRings } from './plan/WorkTypeRings';
import { PhaseTimeline } from './plan/PhaseTimeline';
import { ProjectTasksTable } from './plan/ProjectTasksTable';
import { DARK_THEME } from '../../utils/constants';

const cardStyle = {
  background: DARK_THEME.cardBg,
  border: '1px solid rgba(255,255,255,0.06)',
};

const cardTitle = (text: string) => (
  <span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>{text}</span>
);

interface Props {
  projectKey: string;
  year: number;
  quarter: number;
}

export const ProjectPlanView: React.FC<Props> = ({ projectKey, year, quarter }) => {
  const { data, isLoading } = useProjectPlan(projectKey, year, quarter);

  if (isLoading || !data) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <WorkTypeRings
        workTypes={data.work_types}
        externalHours={data.external_hours}
        totalPlan={data.total_plan}
        totalFact={data.total_fact}
        totalPct={data.total_pct}
      />

      <Card
        size="small"
        title={cardTitle('Таймлайн проекта')}
        style={cardStyle}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <PhaseTimeline timeline={data.timeline} mode="by-phase" />
      </Card>

      <Card
        size="small"
        title={cardTitle(`Задачи проекта · ${data.children.length}`)}
        style={cardStyle}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <ProjectTasksTable children={data.children} />
      </Card>
    </div>
  );
};
