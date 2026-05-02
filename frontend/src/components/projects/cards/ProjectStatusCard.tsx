import React from 'react';
import { Card } from 'antd';
import type { ProjectDetail, ProjectSummary } from '../../../types/projects';

interface Props {
  summary: ProjectSummary | null | undefined;
  detail: ProjectDetail;
}

interface TileProps {
  value: string | number;
  label: string;
  color?: string;
}

const KpiTile: React.FC<TileProps> = ({ value, label, color }) => (
  <div
    style={{
      background: '#091527',
      borderRadius: 8,
      padding: '10px 12px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
    }}
  >
    <div style={{ fontSize: 22, fontWeight: 700, color: color ?? '#fff', lineHeight: 1 }}>{value}</div>
    <div style={{ fontSize: 11, color: '#7e94b8', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
      {label}
    </div>
  </div>
);

export const ProjectStatusCard: React.FC<Props> = ({ summary, detail }) => {
  return (
    <Card
      size="small"
      title={<span style={{ color: '#cfd8e5', fontSize: 13 }}>Статус проекта</span>}
      style={{ background: '#0f2340', border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {summary?.status_text && (
          <p style={{ margin: 0, color: '#67d68d', fontSize: 13, lineHeight: 1.5 }}>
            {summary.status_text}
          </p>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <KpiTile value={detail.child_count} label="Задач" />
          <KpiTile value={`${detail.total_hours} ч`} label="Часов" color="#faad14" />
          <KpiTile value={detail.employee_count} label="Участников" />
          <KpiTile value={`${detail.weeks} нед`} label="Недель" />
        </div>
      </div>
    </Card>
  );
};
