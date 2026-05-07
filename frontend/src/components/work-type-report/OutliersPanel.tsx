import { Tag } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { Outlier } from '../../types/workTypeReport';

// Reason code → human label (from app/services/work_type_outlier_detector.py)
const REASON_LABELS: Record<string, string> = {
  high_hours: 'Часы выше нормы',
  many_reopens: 'Часто переоткрывалась',
  many_workers: 'Много исполнителей',
  stale: 'Долго без активности',
  // legacy codes in case snapshot was built with old detector
  hours_high: 'Часы выше нормы',
  reopen_count: 'Часто переоткрывалась',
  workers_many: 'Много исполнителей',
  stale_dormant: 'Долго без активности',
};

interface Props {
  outliers: Outlier[];
  /** Map from issue_id → summary, built by the page from themes */
  summaryById: Map<string, string>;
  onOutlierClick?: (issueId: string, issueKey: string) => void;
}

export default function OutliersPanel({ outliers, summaryById, onOutlierClick }: Props) {
  if (outliers.length === 0) {
    return (
      <div
        style={{
          color: DARK_THEME.textMuted,
          fontSize: 13,
          padding: '12px 0',
          textAlign: 'center',
        }}
      >
        Аномалий не обнаружено
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {outliers.map((o) => {
        const label = REASON_LABELS[o.reason] ?? o.reason;
        const summary = summaryById.get(o.issue_id);
        const ctxThreshold =
          o.context && typeof o.context.threshold === 'number'
            ? ` · порог ${o.context.threshold}`
            : '';

        return (
          <div
            key={`${o.issue_id}:${o.reason}`}
            onClick={() => onOutlierClick?.(o.issue_id, o.key)}
            style={{
              background: DARK_THEME.darkAccent,
              border: `1px solid ${DARK_THEME.border}`,
              borderRadius: 6,
              padding: '10px 12px',
              cursor: onOutlierClick ? 'pointer' : 'default',
              transition: 'border-color 0.15s',
            }}
            onMouseEnter={(e) => {
              if (onOutlierClick) {
                (e.currentTarget as HTMLDivElement).style.borderColor = DARK_THEME.cyanPrimary;
              }
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLDivElement).style.borderColor = DARK_THEME.border;
            }}
          >
            {/* Top row: key + reason badge */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span
                style={{
                  fontFamily: 'monospace',
                  fontWeight: 700,
                  color: DARK_THEME.cyanPrimary,
                  fontSize: 13,
                }}
              >
                {o.key}
              </span>
              <Tag
                color="red"
                style={{ marginInlineEnd: 0, fontSize: 11, padding: '1px 6px' }}
              >
                {label}
              </Tag>
            </div>

            {/* Summary */}
            {summary && (
              <div
                style={{
                  color: DARK_THEME.textSecondary,
                  fontSize: 12,
                  marginBottom: 4,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={summary}
              >
                {summary}
              </div>
            )}

            {/* Meta row */}
            <div
              style={{
                display: 'flex',
                gap: 4,
                color: DARK_THEME.textMuted,
                fontSize: 11,
                flexWrap: 'wrap',
              }}
            >
              <span>
                Значение: <strong style={{ color: DARK_THEME.textSecondary }}>{o.value}</strong>
                {ctxThreshold}
              </span>
              {o.explanation && (
                <span style={{ fontStyle: 'italic', color: DARK_THEME.textHint }}>
                  · {o.explanation}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
