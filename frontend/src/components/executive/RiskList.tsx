import { Card, Tag, Typography } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { ExecutiveRisk } from '../../api/executive';

export interface RiskListProps {
  risks: ExecutiveRisk[];
}

const LEVEL_COLOR: Record<ExecutiveRisk['level'], string> = {
  red: '#E24B4A',
  yellow: DARK_THEME.yellow,
  green: DARK_THEME.success,
};

const LEVEL_LABEL: Record<ExecutiveRisk['level'], string> = {
  red: 'Высокий',
  yellow: 'Средний',
  green: 'Низкий',
};

export default function RiskList({ risks }: RiskListProps) {
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
        Топ рисков
      </Typography.Text>
      {risks.length === 0 ? (
        <Typography.Text style={{ color: DARK_THEME.textMuted, fontSize: 13 }}>
          Рисков не выявлено
        </Typography.Text>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {risks.map((r, idx) => {
            const accent = LEVEL_COLOR[r.level] ?? DARK_THEME.textMuted;
            return (
              <div
                key={`${r.key ?? idx}-${idx}`}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '8px 1fr',
                  gap: 10,
                  padding: '10px 12px',
                  background: DARK_THEME.darkAccent,
                  border: `1px solid ${DARK_THEME.border}`,
                  borderRadius: 6,
                }}
              >
                <span
                  style={{
                    width: 4,
                    background: accent,
                    borderRadius: 2,
                    alignSelf: 'stretch',
                  }}
                />
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      marginBottom: 4,
                      flexWrap: 'wrap',
                    }}
                  >
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: DARK_THEME.textPrimary,
                      }}
                    >
                      {r.title}
                    </span>
                    <Tag color={r.level === 'red' ? 'red' : r.level === 'yellow' ? 'gold' : 'green'} style={{ margin: 0 }}>
                      {LEVEL_LABEL[r.level]}
                    </Tag>
                  </div>
                  <div style={{ fontSize: 12, color: DARK_THEME.textMuted, marginBottom: 4 }}>
                    {r.impact}
                  </div>
                  <div style={{ fontSize: 11, color: DARK_THEME.textHint }}>
                    Ответственный: {r.owner} · {r.action}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
