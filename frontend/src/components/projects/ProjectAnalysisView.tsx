import React from 'react';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';
import { ProjectGoalsCard } from './cards/ProjectGoalsCard';
import { ProjectCategoriesCard } from './cards/ProjectCategoriesCard';
import { ProjectEmployeesCard } from './cards/ProjectEmployeesCard';
import { ProjectResultCard } from './cards/ProjectResultCard';
import { ProjectStatusCard } from './cards/ProjectStatusCard';
import { ProjectKeyBlocksCard } from './cards/ProjectKeyBlocksCard';
import { ProjectRatingsCard } from './cards/ProjectRatingsCard';
import { ProjectTopIssuesCard } from './cards/ProjectTopIssuesCard';

interface Props {
  detail: ProjectDetail | undefined;
  summary: ProjectSummary | null | undefined;
}

export const ProjectAnalysisView: React.FC<Props> = ({ detail, summary }) => {
  if (!detail) return null;

  return (
    <div style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <ProjectGoalsCard summary={summary} description={detail.description} />
        <ProjectCategoriesCard
          categories={detail.categories}
          totalHours={detail.total_hours}
          weeks={detail.weeks}
          projectKey={detail.key}
        />
        <ProjectEmployeesCard employees={detail.employees} projectKey={detail.key} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <ProjectResultCard summary={summary} />
        <ProjectStatusCard summary={summary} detail={detail} />
        <ProjectKeyBlocksCard categories={detail.categories} projectKey={detail.key} />
        <ProjectRatingsCard detail={detail} summary={summary} />
        <ProjectTopIssuesCard topIssues={detail.top_issues} projectKey={detail.key} />
      </div>
    </div>
  );
};
