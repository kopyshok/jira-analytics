import { Card, Tag, Typography } from 'antd';
import { DARK_THEME } from '../../utils/constants';

export interface AISummaryProps {
  improved: string;
  risk: string;
  action: string;
  isFallback: boolean;
}

interface SectionConfig {
  label: string;
  body: string;
  accent: string;
  bg: string;
}

function Section({ cfg }: { cfg: SectionConfig }) {
  return (
    <Card
      style={{
        background: cfg.bg,
        border: `1px solid ${cfg.accent}`,
        boxShadow: `inset 2px 0 0 ${cfg.accent}`,
        borderRadius: 8,
        height: '100%',
      }}
      styles={{ body: { padding: '12px 14px' } }}
    >
      <Typography.Text
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: cfg.accent,
          display: 'block',
          marginBottom: 6,
        }}
      >
        {cfg.label}
      </Typography.Text>
      <Typography.Paragraph
        style={{
          fontSize: 13,
          color: DARK_THEME.textPrimary,
          margin: 0,
          lineHeight: 1.5,
          whiteSpace: 'pre-wrap',
        }}
      >
        {cfg.body}
      </Typography.Paragraph>
    </Card>
  );
}

export default function AISummary(props: AISummaryProps) {
  const { improved, risk, action, isFallback } = props;

  const sections: SectionConfig[] = [
    { label: 'Что улучшилось', body: improved, accent: DARK_THEME.success, bg: 'rgba(29,158,117,0.08)' },
    { label: 'Где риск', body: risk, accent: DARK_THEME.yellow, bg: 'rgba(245,200,66,0.08)' },
    { label: 'Что делать', body: action, accent: DARK_THEME.textMuted, bg: 'rgba(143,174,200,0.08)' },
  ];

  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 8,
        }}
      >
        <Typography.Text
          style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: DARK_THEME.textHint,
          }}
        >
          AI-сводка
        </Typography.Text>
        {isFallback ? <Tag color="default">fallback</Tag> : null}
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 12,
        }}
      >
        {sections.map((cfg) => (
          <Section key={cfg.label} cfg={cfg} />
        ))}
      </div>
    </div>
  );
}
