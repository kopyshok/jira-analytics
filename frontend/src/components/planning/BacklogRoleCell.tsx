import { Tooltip } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import { useAppTheme } from '../../contexts/ThemeContext';

interface BacklogRoleCellProps {
  label: string;       // 'АН' | 'ПР' | 'ТС' | 'ОПЭ'
  hours: number;
  total: number;       // sum of all 4 roles — used to compute pct
  color: string;       // hex role color
  // Optional Jira-sourced fields — shown in tooltip when present.
  involvement?: number | null;   // 0..1 fraction of working day
  durationDays?: number | null;  // calendar duration in days
}

export default function BacklogRoleCell({ label, hours, total, color, involvement, durationDays }: BacklogRoleCellProps) {
  const pct = total > 0 ? Math.round((hours / total) * 100) : 0;
  const empty = hours === 0;
  // На светлой теме classic-градиент color×aa→color×44 даёт пастельный фон,
  // на нём белый текст не читается. Оставляем тот же градиент (мягкая прозрачность),
  // но текст переключаем на тёмный для light.
  const { mode } = useAppTheme();
  const isLight = mode === 'light';
  const fillText = isLight ? '#1a1f2c' : '#ffffff';
  const filledBg = `linear-gradient(180deg, ${color}aa 0%, ${color}44 100%)`;

  const hasJiraData = (involvement != null) || (durationDays != null);
  const tooltipLines: string[] = [];
  if (durationDays != null) tooltipLines.push(`${durationDays} дн`);
  if (involvement != null) tooltipLines.push(`${Math.round(involvement * 100)}% занятость`);
  const tooltipTitle = hasJiraData ? tooltipLines.join(', ') : undefined;

  const cell = (
    <div
      style={{
        flex: 1,
        minWidth: 52,
        borderRadius: 6,
        padding: '5px 6px 4px',
        textAlign: 'center',
        background: empty
          ? `${color}1a`
          : filledBg,
        border: empty ? `1px solid ${color}55` : `1px solid ${color}cc`,
        borderBottom: empty ? `2px solid ${color}77` : `2px solid ${color}`,
        userSelect: 'none',
      }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 800,
          letterSpacing: '0.07em',
          textTransform: 'uppercase',
          color: empty ? `${color}` : fillText,
          opacity: empty ? 0.6 : 1,
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
            color: empty ? DARK_THEME.textDim : fillText,
          }}
        >
          {empty ? '—' : hours}
        </span>
        {!empty && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 500,
              color: fillText,
              opacity: 0.85,
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
          color: empty ? DARK_THEME.textMuted : fillText,
          opacity: empty ? 0.6 : 0.7,
        }}
      >
        {empty ? '0%' : `${pct}%`}
      </div>
    </div>
  );

  if (!hasJiraData) return cell;

  return (
    <Tooltip title={tooltipTitle}>
      {cell}
    </Tooltip>
  );
}
