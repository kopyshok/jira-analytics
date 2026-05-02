import React from 'react';
import { Spin } from 'antd';
import { useSearchParams } from 'react-router';
import { useProjectDetail } from '../../hooks/useProjects';
import { useProjectSummary } from '../../hooks/useProjectSummary';
import { ProjectHeader } from './ProjectHeader';
import { ProjectAnalysisView } from './ProjectAnalysisView';
import { ProjectPresentationView } from './ProjectPresentationView';

type ViewMode = 'analysis' | 'presentation';

interface Props {
  projectKey: string;
}

export const ProjectDetailPanel: React.FC<Props> = ({ projectKey }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = (searchParams.get('view') as ViewMode) ?? 'analysis';

  const { data: detail, isLoading: detailLoading, error: detailError } = useProjectDetail(projectKey);
  const { data: summary, isLoading: summaryLoading } = useProjectSummary(projectKey);

  const handleViewChange = (v: ViewMode) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('view', v);
      return next;
    });
  };

  if (detailLoading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (detailError || !detail) {
    return (
      <div style={{ flex: 1, padding: 32, color: '#7e94b8' }}>
        Проект не найден или не помечен категорией «Квартальные задачи» / «Архив квартальных задач».
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <ProjectHeader
        detail={detail}
        summary={summary}
        view={view}
        onViewChange={handleViewChange}
      />
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {view === 'analysis' ? (
          <ProjectAnalysisView
            detail={detail}
            summary={summaryLoading ? undefined : summary}
          />
        ) : (
          <ProjectPresentationView
            detail={detail}
            summary={summaryLoading ? undefined : summary}
          />
        )}
      </div>
    </div>
  );
};
