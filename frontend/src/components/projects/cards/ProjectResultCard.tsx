import React from 'react';
import { Card, Empty, Skeleton } from 'antd';
import { CheckCircleFilled } from '@ant-design/icons';
import { useIsFetching } from '@tanstack/react-query';
import type { ProjectSummary } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

interface Props {
  summary: ProjectSummary | null | undefined;
}

export const ProjectResultCard: React.FC<Props> = ({ summary }) => {
  const isFetchingSummary = useIsFetching({ queryKey: ['project-summary'] }) > 0;

  return (
    <Card
      size="small"
      title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Основной результат</span>}
      style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      {!summary && isFetchingSummary ? (
        <Skeleton active paragraph={{ rows: 3 }} title={false} />
      ) : !summary ? (
        <Empty description="AI-резюме генерируется" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {summary.result_checklist && summary.result_checklist.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {summary.result_checklist.map((item, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <CheckCircleFilled
                    style={{
                      color: item.done ? '#67d68d' : 'rgba(255,255,255,0.2)',
                      fontSize: 14,
                      marginTop: 1,
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ color: item.done ? 'var(--text-2, #cfd8e5)' : DARK_THEME.textMuted, fontSize: 13 }}>{item.label}</span>
                </div>
              ))}
            </div>
          )}
          {summary.status_text && (
            <div
              style={{
                marginTop: 4,
                paddingTop: 8,
                borderTop: '1px solid rgba(255,255,255,0.06)',
                color: 'var(--text-2, #cfd8e5)',
                fontSize: 12,
                lineHeight: 1.5,
              }}
            >
              {summary.status_text}
            </div>
          )}
        </div>
      )}
    </Card>
  );
};
