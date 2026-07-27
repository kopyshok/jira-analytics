import React from 'react';
import type { PortfolioSignal } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

const DOT_COLOR: Record<string, string> = {
  warn: '#faad14',
  info: DARK_THEME.cyanPrimary,
};

export const PortfolioSignals: React.FC<{ signals: PortfolioSignal[] }> = ({ signals }) => {
  if (signals.length === 0) return null;
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {signals.map((s) => (
        <span
          key={s.kind}
          style={{
            display: 'flex', alignItems: 'center', gap: 7,
            fontSize: 12, color: DARK_THEME.textPrimary,
            padding: '5px 12px', borderRadius: 14,
            background: 'rgba(255,255,255,0.04)',
            border: `1px solid ${DARK_THEME.border}`,
          }}
        >
          <span style={{
            width: 7, height: 7, borderRadius: '50%',
            background: DOT_COLOR[s.severity] ?? DARK_THEME.textMuted,
          }} />
          {s.text}
        </span>
      ))}
    </div>
  );
};
