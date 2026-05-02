import React from 'react';
import { Card, Empty } from 'antd';
import { useNavigate } from 'react-router';
import type { TopIssue } from '../../../types/projects';

interface Props {
  topIssues: TopIssue[];
  projectKey: string;
}

export const ProjectTopIssuesCard: React.FC<Props> = ({ topIssues }) => {
  const navigate = useNavigate();
  const top3 = (topIssues ?? []).slice(0, 3);

  return (
    <Card
      size="small"
      title={<span style={{ color: '#cfd8e5', fontSize: 13 }}>Топ-3 задачи по трудозатратам</span>}
      style={{ background: '#0f2340', border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      {top3.length === 0 ? (
        <Empty description="Нет данных" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {top3.map((issue, i) => (
            <div
              key={issue.key}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                cursor: 'pointer',
                padding: '6px 8px',
                borderRadius: 6,
                transition: 'background 0.15s',
              }}
              onClick={() => navigate(`/analytics?issue=${issue.key}`)}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.04)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
            >
              <span style={{ color: '#7e94b8', fontSize: 12, minWidth: 18, marginTop: 1 }}>{i + 1}.</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ color: '#00c9c8', fontSize: 12, fontWeight: 600 }}>{issue.key}</span>
                {' '}
                <span style={{ color: '#cfd8e5', fontSize: 12 }}>{issue.summary}</span>
              </div>
              <span style={{ color: '#7e94b8', fontSize: 11, whiteSpace: 'nowrap', marginLeft: 4 }}>
                {issue.hours} ч
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};
