import { DARK_THEME } from '../../utils/constants';

interface Props {
  collapsed?: boolean;
}

/**
 * Brand mark: a geometric cyan glyph — two offset concentric arcs evoking
 * orbit/tracking, paired with a wordmark set in the display serif.
 */
export default function LogoMark({ collapsed = false }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        height: 56,
        padding: '0 16px',
        borderBottom: `1px solid ${DARK_THEME.border}`,
        boxSizing: 'border-box',
      }}
    >
      <svg width="28" height="28" viewBox="0 0 32 32" fill="none" style={{ flexShrink: 0 }}>
        <circle cx="16" cy="16" r="13" stroke={DARK_THEME.cyanPrimary} strokeWidth="1.5" opacity="0.35" />
        <path
          d="M5 16a11 11 0 0 1 22 0"
          stroke={DARK_THEME.cyanPrimary}
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="16" cy="5" r="2.5" fill={DARK_THEME.cyanPrimary} />
        <circle cx="16" cy="16" r="2" fill={DARK_THEME.amber} />
      </svg>
      {!collapsed && (
        <div style={{ minWidth: 0, lineHeight: 1.1 }}>
          <div
            style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 17,
              fontWeight: 600,
              color: DARK_THEME.textPrimary,
              letterSpacing: '-0.01em',
            }}
          >
            Jira
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 6,
              marginTop: 1,
            }}
          >
            <span
              style={{
                fontSize: 10,
                textTransform: 'uppercase',
                letterSpacing: '0.18em',
                color: DARK_THEME.cyanPrimary,
                fontWeight: 600,
              }}
            >
              Analytics
            </span>
            <span
              title={`Версия ${__APP_VERSION__}`}
              style={{
                fontSize: 9,
                color: DARK_THEME.textMuted,
                fontWeight: 500,
                letterSpacing: '0.04em',
              }}
            >
              v{__APP_VERSION__}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
