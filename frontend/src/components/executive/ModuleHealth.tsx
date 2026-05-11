import { Card, Progress, Typography } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { ExecutiveModule } from '../../api/executive';

export interface ModuleHealthProps {
  modules: ExecutiveModule[];
}

const HEALTH_COLOR: Record<ExecutiveModule['health'], string> = {
  green: DARK_THEME.success,
  yellow: DARK_THEME.yellow,
  red: DARK_THEME.danger,
};

function parsePct(load: string): number {
  const n = parseInt(load.replace('%', ''), 10);
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0;
}

export default function ModuleHealth({ modules }: ModuleHealthProps) {
  return (
    <Card
      style={{
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 8,
        height: '100%',
      }}
      styles={{ body: { padding: '14px 16px' } }}
    >
      <Typography.Text
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: DARK_THEME.textHint,
          display: 'block',
          marginBottom: 12,
        }}
      >
        Здоровье модулей
      </Typography.Text>
      {modules.length === 0 ? (
        <Typography.Text style={{ color: DARK_THEME.textMuted, fontSize: 13 }}>
          Нет данных
        </Typography.Text>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {modules.map((m) => {
            const dotColor = HEALTH_COLOR[m.health] ?? DARK_THEME.textMuted;
            const pct = parsePct(m.load);
            return (
              <div
                key={m.name}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '12px 1fr 70px 90px',
                  alignItems: 'center',
                  gap: 10,
                }}
              >
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: '50%',
                    background: dotColor,
                  }}
                />
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 13,
                      color: DARK_THEME.textPrimary,
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {m.name}
                  </div>
                  <div style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                    {m.note}
                  </div>
                </div>
                <span
                  style={{
                    fontSize: 12,
                    color: dotColor,
                    fontWeight: 600,
                  }}
                >
                  {m.risk}
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Progress
                    percent={pct}
                    showInfo={false}
                    size="small"
                    strokeColor={DARK_THEME.cyanPrimary}
                    trailColor={DARK_THEME.darkRows}
                    style={{ flex: 1, margin: 0 }}
                  />
                  <span style={{ fontSize: 11, color: DARK_THEME.textMuted, minWidth: 32, textAlign: 'right' }}>
                    {m.load}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
