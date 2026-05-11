import React from 'react';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';
import { ProjectGoalsCard } from './cards/ProjectGoalsCard';
import { ProjectCategoriesCard } from './cards/ProjectCategoriesCard';
import { ProjectEmployeesCard } from './cards/ProjectEmployeesCard';
import { ProjectResultCard } from './cards/ProjectResultCard';
import { ProjectStatusCard } from './cards/ProjectStatusCard';
import { ProjectRatingsCard } from './cards/ProjectRatingsCard';
import { ProjectTopIssuesCard } from './cards/ProjectTopIssuesCard';

interface Props {
  detail: ProjectDetail | undefined;
  summary: ProjectSummary | null | undefined;
}

export const ProjectAnalysisView: React.FC<Props> = ({ detail, summary }) => {
  if (!detail) return null;

  return (
    <div
      style={{
        padding: 16,
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: 16,
        alignItems: 'start',
      }}
    >
      <ProjectGoalsCard summary={summary} description={detail.description} />
      <ProjectResultCard summary={summary} />
      <ProjectCategoriesCard
        categories={detail.categories}
        totalHours={detail.total_hours}
        weeks={detail.weeks}
        projectKey={detail.key}
        summary={summary}
        issueHoursByKey={detail.issue_hours_by_key}
      />
      <ProjectStatusCard summary={summary} detail={detail} />
      <ProjectEmployeesCard employees={detail.employees} projectKey={detail.key} />
      <ProjectRatingsCard detail={detail} summary={summary} />
      <ProjectTopIssuesCard topIssues={detail.top_issues} projectKey={detail.key} />
    </div>
  );
};
