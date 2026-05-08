import type { ReactNode } from 'react';
import { Card, Typography } from 'antd';
import { DARK_THEME, FONTS } from '../../utils/constants';

export type KpiStatus = 'good' | 'warn' | 'bad';

export interface KpiCardProps {
  icon?: ReactNode;
  title: string;
  value: string;
  deltaText?: string;
  status: KpiStatus;
  detail: string;
}

const STATUS_COLORS: Record<KpiStatus, { accent: string; bg: string }> = {
  good: { accent: DARK_THEME.success, bg: 'rgba(29,158,117,0.12)' },
  warn: { accent: DARK_THEME.yellow, bg: 'rgba(245,200,66,0.12)' },
  bad: { accent: '#E24B4A', bg: 'rgba(226,75,74,0.12)' },
};

export default function KpiCard(props: KpiCardProps) {
  const { icon, title, value, deltaText, status, detail } = props;
  const colors = STATUS_COLORS[status];

  return (
    <Card
      style={{
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 8,
        height: '100%',
      }}
      styles={{ body: { padding: '14px 16px' } }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        {icon ? (
          <span
            style={{
              width: 28,
              height: 28,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 6,
              background: colors.bg,
              color: colors.accent,
              fontSize: 16,
            }}
          >
            {icon}
          </span>
        ) : null}
        <Typography.Text
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: DARK_THEME.textHint,
          }}
        >
          {title}
        </Typography.Text>
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          marginBottom: 6,
        }}
      >
        <span
          style={{
            fontFamily: FONTS.display,
            fontSize: 30,
            fontWeight: 600,
            color: DARK_THEME.textPrimary,
            lineHeight: 1,
          }}
        >
          {value}
        </span>
        {deltaText ? (
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: colors.accent,
              padding: '2px 8px',
              borderRadius: 12,
              background: colors.bg,
            }}
          >
            {deltaText}
          </span>
        ) : null}
      </div>
      <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
        {detail}
      </Typography.Text>
    </Card>
  );
}
