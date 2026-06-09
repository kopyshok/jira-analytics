import React from 'react';
import { Card, Empty } from 'antd';
import { useNavigate } from 'react-router';
import type { CategoryBreakdown, ProjectSummary, IssueHours } from '../../../types/projects';
import { DonutChart } from '../shared/DonutChart';
import { DARK_THEME } from '../../../utils/constants';

interface Props {
  categories: CategoryBreakdown[];
  totalHours: number;
  weeks: number;
  projectKey: string;
  summary?: ProjectSummary | null;
  issueHoursByKey?: IssueHours[];
}

const DEFAULT_COLOR = DARK_THEME.textMuted;
const AI_PALETTE = ['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', '#ff4d4f', '#67d68d'];

export const ProjectCategoriesCard: React.FC<Props> = ({
  categories,
  totalHours,
  weeks,
  projectKey,
  summary,
  issueHoursByKey,
}) => {
  const navigate = useNavigate();

  const groups = summary?.work_breakdown ?? [];
  const useAI = groups.length > 0 && issueHoursByKey && issueHoursByKey.length > 0;

  const slices = useAI
    ? (() => {
        const hoursMap = new Map(issueHoursByKey!.map((r) => [r.key, r.hours]));
        const raw = groups.map((g, i) => {
          const hours = g.child_keys.reduce((acc, k) => acc + (hoursMap.get(k) ?? 0), 0);
          return {
            code: g.label,
            label: g.label,
            hours: Math.round(hours),
            color: AI_PALETTE[i % AI_PALETTE.length],
            pct: 0,
          };
        });
        const total = raw.reduce((acc, s) => acc + s.hours, 0);
        return raw.map((s) => ({ ...s, pct: total ? Math.round((s.hours / total) * 100) : 0 }));
      })()
    : categories.map((c) => ({
        code: c.code,
        label: c.label,
        hours: Math.round(c.hours),
        color: c.color ?? DEFAULT_COLOR,
        pct: c.pct,
      }));

  if (slices.length === 0) {
    return (
      <Card
        size="small"
        title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Структура трудозатрат</span>}
        style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <Empty description="Нет данных" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const handleSliceClick = useAI
    ? undefined
    : (slice: { code: string }) => {
        navigate(`/analytics?category=${slice.code}&project=${projectKey}`);
      };

  return (
    <Card
      size="small"
      title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Структура трудозатрат</span>}
      style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
        <DonutChart
          slices={slices}
          centerValue={`${Math.round(totalHours)} ч`}
          centerLabel={`~${weeks} нед`}
          size={160}
          onSliceClick={handleSliceClick}
        />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {slices.map((s) => {
            const openCategory = useAI
              ? undefined
              : () => navigate(`/analytics?category=${s.code}&project=${projectKey}`);
            return (
              <div
                key={s.code}
                role={openCategory ? 'button' : undefined}
                tabIndex={openCategory ? 0 : undefined}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  cursor: useAI ? 'default' : 'pointer',
                }}
                onClick={openCategory}
                onKeyDown={
                  openCategory
                    ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          openCategory();
                        }
                      }
                    : undefined
                }
              >
                <div
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: s.color,
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    flex: 1,
                    color: 'var(--text-2, #cfd8e5)',
                    fontSize: 12,
                    minWidth: 0,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {s.label}
                </span>
                <span style={{ color: DARK_THEME.textMuted, fontSize: 11, whiteSpace: 'nowrap' }}>
                  {s.hours} ч · {s.pct}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
};
