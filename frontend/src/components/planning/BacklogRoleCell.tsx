import { DARK_THEME } from '../../utils/constants';

interface BacklogRoleCellProps {
  label: string;       // 'АН' | 'ПР' | 'ТС' | 'ОПЭ'
  hours: number;
  total: number;       // sum of all 4 roles — used to compute pct
  color: string;       // hex role color
}

export default function BacklogRoleCell({ label, hours, total, color }: BacklogRoleCellProps) {
  const pct = total > 0 ? Math.round((hours / total) * 100) : 0;
  const empty = hours === 0;

  return (
    <div
      style={{
        flex: 1,
        minWidth: 52,
        borderRadius: 6,
        padding: '5px 6px 4px',
        textAlign: 'center',
        background: empty
          ? `${color}0d`
          : `linear-gradient(180deg, ${color}55 0%, ${color}22 100%)`,
        border: empty ? `1px solid ${color}33` : `1px solid ${color}66`,
        borderBottom: empty ? `2px solid ${color}44` : `2px solid ${color}`,
        userSelect: 'none',
      }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 800,
          letterSpacing: '0.07em',
          textTransform: 'uppercase',
          color,
          opacity: empty ? 0.45 : 0.95,
          marginBottom: 2,
        }}
      >
        {label}
      </div>
      <div style={{ lineHeight: 1, marginBottom: 2 }}>
        <span
          style={{
            fontSize: 16,
            fontWeight: 800,
            color: empty ? DARK_THEME.textDim : color,
          }}
        >
          {empty ? '—' : hours}
        </span>
        {!empty && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 500,
              color,
              opacity: 0.65,
              marginLeft: 3,
            }}
          >
            ч
          </span>
        )}
      </div>
      <div
        style={{
          fontSize: 10,
          color: DARK_THEME.textMuted,
          opacity: 0.6,
        }}
      >
        {empty ? '0%' : `${pct}%`}
      </div>
    </div>
  );
}
