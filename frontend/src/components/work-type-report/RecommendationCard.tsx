import { BulbOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  recommendation: { text: string; expected_impact: string };
}

export default function RecommendationCard({ recommendation }: Props) {
  const { text, expected_impact } = recommendation;
  if (!text && !expected_impact) return null;

  return (
    <div
      style={{
        borderLeft: `4px solid ${DARK_THEME.yellow}`,
        borderTop: `1px solid ${DARK_THEME.border}`,
        borderRight: `1px solid ${DARK_THEME.border}`,
        borderBottom: `1px solid ${DARK_THEME.border}`,
        borderRadius: '0 6px 6px 0',
        background: DARK_THEME.darkAccent,
        padding: '12px 14px',
        marginBottom: 8,
      }}
    >
      {/* Title */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          marginBottom: 8,
          fontWeight: 700,
          fontSize: 13,
          color: DARK_THEME.yellow,
        }}
      >
        <BulbOutlined />
        <span>Рекомендация</span>
      </div>

      {/* Body */}
      {text && (
        <div
          style={{
            color: DARK_THEME.textPrimary,
            fontSize: 13,
            lineHeight: 1.5,
            marginBottom: expected_impact ? 10 : 0,
          }}
        >
          {text}
        </div>
      )}

      {/* Expected impact */}
      {expected_impact && (
        <div style={{ fontSize: 12 }}>
          <span style={{ color: DARK_THEME.textMuted }}>Ожидаемый эффект: </span>
          <span style={{ color: DARK_THEME.textSecondary }}>{expected_impact}</span>
        </div>
      )}
    </div>
  );
}
