import { DARK_THEME } from '../../utils/constants';

interface Props {
  visible: boolean;
}

export default function ApproveCelebration({ visible }: Props) {
  if (!visible) return null;
  return (
    <div
      aria-hidden
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        background: 'rgba(13, 28, 51, 0.78)',
        backdropFilter: 'blur(2px)',
        animation: 'celebration-fade 1.6s ease forwards',
        pointerEvents: 'none',
      }}
    >
      <svg width="120" height="120" viewBox="0 0 80 80">
        <circle
          cx="40"
          cy="40"
          r="36"
          fill="none"
          stroke={DARK_THEME.cyanPrimary}
          strokeWidth="3"
          strokeDasharray="226"
          strokeDashoffset="226"
          style={{ animation: 'check-circle-draw 0.5s ease forwards' }}
        />
        <path
          d="M22 40 L36 54 L60 28"
          fill="none"
          stroke={DARK_THEME.cyanPrimary}
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="60"
          strokeDashoffset="60"
          style={{ animation: 'check-mark-draw 0.4s ease 0.45s forwards' }}
        />
      </svg>
      <div
        style={{
          fontSize: 28,
          fontWeight: 700,
          color: DARK_THEME.cyanPrimary,
          letterSpacing: 0.5,
        }}
      >
        Сценарий утверждён
      </div>
    </div>
  );
}
