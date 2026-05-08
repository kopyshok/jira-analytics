import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { Progress } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { Theme } from '../../types/workTypeReport';

interface Props {
  themes: Theme[];
  totalHours: number;
  onThemeClick?: (themeId: string | null) => void;
}

const OTHER_COLOR = '#4a6a8a';
const MAX_TOP = 5;

interface Slice {
  themeId: string | null;
  name: string;
  hours: number;
  pct: number;
  color: string;
}

function buildSlices(themes: Theme[], totalHours: number): Slice[] {
  const sorted = [...themes].sort((a, b) => b.totals.hours - a.totals.hours);
  const top = sorted.slice(0, MAX_TOP);
  const rest = sorted.slice(MAX_TOP);

  const slices: Slice[] = top.map((t) => ({
    themeId: t.theme_id,
    name: t.name,
    hours: t.totals.hours,
    pct: t.totals.pct,
    color: t.color,
  }));

  if (rest.length > 0) {
    const otherHours = rest.reduce((s, t) => s + t.totals.hours, 0);
    const otherPct = totalHours > 0 ? (otherHours / totalHours) * 100 : 0;
    slices.push({
      themeId: null,
      name: 'Другое',
      hours: otherHours,
      pct: otherPct,
      color: OTHER_COLOR,
    });
  }

  return slices;
}

export default function ThemeDistribution({ themes, totalHours, onThemeClick }: Props) {
  if (themes.length === 0) {
    return (
      <div
        style={{
          background: DARK_THEME.cardBg,
          border: `1px solid ${DARK_THEME.border}`,
          borderRadius: 8,
          padding: 24,
          minHeight: 280,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          color: DARK_THEME.textMuted,
        }}
      >
        <div>
          <div style={{ fontSize: 32, marginBottom: 12 }}>★</div>
          <div style={{ fontSize: 14, marginBottom: 6, color: DARK_THEME.textSecondary }}>
            Темы ещё не приняты
          </div>
          <div style={{ fontSize: 12 }}>
            Откройте «Словарь тем» → вкладка «Кандидаты»,
            <br />
            примите подходящие — диаграмма появится здесь
          </div>
        </div>
      </div>
    );
  }

  const slices = buildSlices(themes, totalHours);
  const centerLabel = `${Math.round(totalHours)} ч`;

  return (
    <div
      style={{
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 8,
        padding: '16px',
        marginBottom: 16,
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, color: DARK_THEME.textMuted, marginBottom: 12 }}>
        Распределение тем
      </div>

      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        {/* Donut */}
        <div style={{ position: 'relative', width: 160, height: 160, flexShrink: 0 }}>
          <ResponsiveContainer width={160} height={160}>
            <PieChart>
              <Pie
                data={slices}
                dataKey="hours"
                innerRadius={50}
                outerRadius={72}
                paddingAngle={1}
                stroke="none"
                isAnimationActive={false}
              >
                {slices.map((s, i) => (
                  <Cell
                    key={i}
                    fill={s.color}
                    onClick={() => onThemeClick?.(s.themeId)}
                    style={{ cursor: onThemeClick ? 'pointer' : undefined }}
                  />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          {/* Center label */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              pointerEvents: 'none',
            }}
          >
            <div style={{ fontSize: 18, fontWeight: 700, color: DARK_THEME.textPrimary }}>
              {centerLabel}
            </div>
          </div>
        </div>

        {/* Bars list */}
        <div style={{ flex: 1, minWidth: 160 }}>
          {slices.map((s) => (
            <div
              key={s.themeId ?? '__other__'}
              style={{ marginBottom: 10, cursor: onThemeClick ? 'pointer' : undefined }}
              onClick={() => onThemeClick?.(s.themeId)}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: 12,
                  marginBottom: 3,
                }}
              >
                <span
                  style={{
                    color: DARK_THEME.textSecondary,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: '60%',
                  }}
                  title={s.name}
                >
                  {s.name}
                </span>
                <span style={{ color: DARK_THEME.textMuted, flexShrink: 0 }}>
                  {Math.round(s.hours)} ч ({s.pct.toFixed(1)}%)
                </span>
              </div>
              <Progress
                percent={s.pct}
                showInfo={false}
                size="small"
                strokeColor={s.color}
                trailColor={DARK_THEME.border}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
