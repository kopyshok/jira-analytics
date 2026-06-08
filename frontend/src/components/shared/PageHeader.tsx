import type { ReactNode } from 'react';
import { DARK_THEME } from '../../utils/constants';
import { useAppTheme } from '../../contexts/ThemeContext';

interface Props {
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

/**
 * Strip across the top of every page: tiny uppercase eyebrow, large serif
 * display title, optional muted subtitle, and a right-aligned action slot.
 *
 * Aurora-mode rendering: glass-token colors + Fraunces 30px title (no
 * separator border, blends into the glass card below).
 */
export default function PageHeader({ eyebrow, title, subtitle, actions }: Props) {
  const { isAurora } = useAppTheme();

  if (isAurora) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 16,
          marginBottom: 20,
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          {eyebrow && (
            <div className="eyebrow" style={{ marginBottom: 5 }}>{eyebrow}</div>
          )}
          <div
            className="serif"
            style={{ fontSize: 30, fontWeight: 600, letterSpacing: '-0.02em' }}
          >
            {title}
          </div>
          {subtitle && (
            <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 13 }}>
              {subtitle}
            </div>
          )}
        </div>
        {actions && <div style={{ flexShrink: 0 }}>{actions}</div>}
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: 24,
        marginBottom: 12,
        paddingBottom: 10,
        borderBottom: `1px solid ${DARK_THEME.border}`,
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        {eyebrow && (
          <div
            style={{
              fontSize: 11,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              color: DARK_THEME.cyanPrimary,
              fontWeight: 600,
              marginBottom: 6,
            }}
          >
            {eyebrow}
          </div>
        )}
        <h1 className="page-title">{title}</h1>
        {subtitle && <div className="page-subtitle">{subtitle}</div>}
      </div>
      {actions && <div style={{ flexShrink: 0 }}>{actions}</div>}
    </div>
  );
}
