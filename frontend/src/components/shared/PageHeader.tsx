import type { ReactNode } from 'react';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

/**
 * Strip across the top of every page: tiny uppercase eyebrow, large serif
 * display title, optional muted subtitle, and a right-aligned action slot.
 */
export default function PageHeader({ eyebrow, title, subtitle, actions }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: 24,
        marginBottom: 28,
        paddingBottom: 20,
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
