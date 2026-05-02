import React from 'react';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';

interface Props {
  detail: ProjectDetail | undefined;
  summary: ProjectSummary | null | undefined;
}

export const ProjectPresentationView: React.FC<Props> = ({ detail }) => (
  <div style={{ padding: 16, color: '#7e94b8' }}>
    Presentation view для {detail?.key} — заглушка, Phase 6
  </div>
);
