import React from 'react';
import { Card } from 'antd';
import type { ProjectDetail, ProjectSummary } from '../../../types/projects';
import { StarRating } from '../shared/StarRating';

interface Props {
  detail: ProjectDetail;
  summary: ProjectSummary | null | undefined;
}

interface RatingRowProps {
  label: string;
  value: number | null;
}

const RatingRow: React.FC<RatingRowProps> = ({ label, value }) => {
  if (value === null) return null;
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: '#cfd8e5', fontSize: 13 }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StarRating value={value} size={18} />
        <span style={{ color: '#7e94b8', fontSize: 12, minWidth: 28 }}>{value}/5</span>
      </div>
    </div>
  );
};

export const ProjectRatingsCard: React.FC<Props> = ({ detail, summary }) => {
  const { rating_quality, rating_speed, rating_result } = detail;

  if (rating_quality === null && rating_speed === null && rating_result === null) {
    return null;
  }

  return (
    <Card
      size="small"
      title={<span style={{ color: '#cfd8e5', fontSize: 13 }}>Оценка заказчика</span>}
      style={{ background: '#0f2340', border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <RatingRow label="Качество" value={rating_quality} />
        <RatingRow label="Скорость" value={rating_speed} />
        <RatingRow label="Результат" value={rating_result} />
        {summary?.workload_summary && (
          <div
            style={{
              background: '#091527',
              borderRadius: 6,
              padding: '8px 10px',
              color: '#7e94b8',
              fontSize: 12,
              lineHeight: 1.5,
              marginTop: 4,
            }}
          >
            {summary.workload_summary}
          </div>
        )}
      </div>
    </Card>
  );
};
