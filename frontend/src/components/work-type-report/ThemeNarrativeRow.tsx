import React from 'react';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  themeId: string | null;
  narrative: string;
  evidenceKeys: string[];
  onIssueClick?: (issueKey: string) => void;
}

function renderNarrative(
  text: string,
  onIssueClick?: (k: string) => void,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(/\b([A-Z][A-Z0-9]+-\d+)\b/g)) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const key = match[1];
    parts.push(
      <a
        key={`${key}-${match.index}`}
        style={{ color: DARK_THEME.cyanPrimary, cursor: 'pointer', fontStyle: 'normal' }}
        onClick={() => onIssueClick?.(key)}
      >
        {key}
      </a>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

export default function ThemeNarrativeRow({ narrative, evidenceKeys, onIssueClick }: Props) {
  if (!narrative) {
    return (
      <div
        style={{
          background: 'rgba(0,201,200,0.03)',
          padding: '12px 16px',
          fontStyle: 'italic',
          color: DARK_THEME.textMuted,
          fontSize: 12,
        }}
      >
        «AI-narrative недоступен»
      </div>
    );
  }

  return (
    <div
      style={{
        background: 'rgba(0,201,200,0.03)',
        padding: '12px 16px',
        fontStyle: 'italic',
        color: DARK_THEME.textSecondary,
        fontSize: 13,
        lineHeight: 1.6,
      }}
    >
      <span>{renderNarrative(narrative, onIssueClick)}</span>
      {evidenceKeys.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 12, color: DARK_THEME.textMuted }}>
          <span style={{ fontStyle: 'normal', fontWeight: 500 }}>Сильнее всего: </span>
          {evidenceKeys.map((k, idx) => (
            <React.Fragment key={k}>
              {idx > 0 && <span style={{ fontStyle: 'normal', margin: '0 4px' }}>·</span>}
              <a
                style={{ color: DARK_THEME.cyanPrimary, cursor: 'pointer', fontStyle: 'normal' }}
                onClick={() => onIssueClick?.(k)}
              >
                {k}
              </a>
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
