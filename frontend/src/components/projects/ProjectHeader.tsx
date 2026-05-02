import React from 'react';
import { Tag, Button } from 'antd';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';

type ViewMode = 'analysis' | 'presentation';

interface Props {
  detail: ProjectDetail | undefined;
  summary: ProjectSummary | null | undefined;
  view: ViewMode;
  onViewChange: (v: ViewMode) => void;
}

export const ProjectHeader: React.FC<Props> = ({ detail, view, onViewChange }) => (
  <div
    style={{
      padding: '16px 20px',
      borderBottom: '1px solid rgba(255,255,255,0.06)',
      display: 'flex',
      alignItems: 'flex-start',
      justifyContent: 'space-between',
      gap: 12,
    }}
  >
    <div style={{ minWidth: 0 }}>
      <div
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: '#e8f0fa',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {detail?.summary ?? '—'}
      </div>
      <div style={{ fontSize: 12, color: '#7e94b8', marginTop: 4 }}>
        <span style={{ color: '#4db8e8' }}>{detail?.key}</span>
        {detail?.status && (
          <Tag style={{ marginLeft: 8, fontSize: 11 }}>{detail.status}</Tag>
        )}
      </div>
    </div>
    <Button
      size="small"
      type={view === 'analysis' ? 'primary' : 'default'}
      onClick={() => onViewChange(view === 'analysis' ? 'presentation' : 'analysis')}
      style={{ flexShrink: 0 }}
    >
      {view === 'analysis' ? 'Презентация' : 'Анализ'}
    </Button>
  </div>
);
