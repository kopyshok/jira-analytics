import React from 'react';
import type { FlowBlock } from '../../../types/projects';

const BG: Record<FlowBlock['status'], string> = {
  source: '#0f2340',
  flow: '#0f2340',
  done: 'rgba(103, 214, 141, 0.16)',
};
const BORDER: Record<FlowBlock['status'], string> = {
  source: '#378ADD',
  flow: '#7e94b8',
  done: '#67d68d',
};

export const FlowDiagram: React.FC<{ blocks: FlowBlock[] }> = ({ blocks }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
    {blocks.map((b, i) => (
      <React.Fragment key={i}>
        <div
          style={{
            padding: '8px 14px',
            borderRadius: 6,
            background: BG[b.status],
            border: `1px solid ${BORDER[b.status]}`,
            color: '#fff',
            fontSize: 13,
            fontWeight: 500,
            whiteSpace: 'nowrap',
          }}
        >
          {b.label}
        </div>
        {i < blocks.length - 1 && <span style={{ color: '#7e94b8' }}>→</span>}
      </React.Fragment>
    ))}
  </div>
);
