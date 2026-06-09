import React from 'react';
import { Card } from 'antd';
import type { ProjectDetail, ProjectSummary } from '../../../types/projects';
import { StarRating } from '../shared/StarRating';
import { DARK_THEME } from '../../../utils/constants';

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
      <span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StarRating value={value} size={18} />
        <span style={{ color: DARK_THEME.textMuted, fontSize: 12, minWidth: 28 }}>{value}/5</span>
      </div>
    </div>
  );
};

export const ProjectRatingsCard: React.FC<Props> = ({ detail, summary }) => {
  const { rating_quality, rating_speed, rating_result } = detail;
  const hasAnyRating = rating_quality !== null || rating_speed !== null || rating_result !== null;

  return (
    <Card
      size="small"
      title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Оценка заказчика</span>}
      style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      {hasAnyRating ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <RatingRow label="Качество" value={rating_quality} />
          <RatingRow label="Скорость" value={rating_speed} />
          <RatingRow label="Результат" value={rating_result} />
          {summary?.workload_summary && (
            <div
              style={{
                background: DARK_THEME.sidebarBg,
                borderRadius: 6,
                padding: '8px 10px',
                color: DARK_THEME.textMuted,
                fontSize: 12,
                lineHeight: 1.5,
                marginTop: 4,
              }}
            >
              {summary.workload_summary}
            </div>
          )}
        </div>
      ) : (
        <div style={{ padding: 16, textAlign: 'center', color: DARK_THEME.textMuted, fontStyle: 'italic', fontSize: 13 }}>
          Оценка заказчика появится после заполнения полей в Jira
        </div>
      )}
    </Card>
  );
};
