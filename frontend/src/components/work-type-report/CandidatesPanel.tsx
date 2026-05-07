import { Button, Card, Tag, Typography } from 'antd';
import { StarOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';
import type { Candidate } from '../../types/workTypeReport';

interface Props {
  candidates: Candidate[];
  onOpenDrawer: () => void;
}

const MAX_VISIBLE = 5;

export default function CandidatesPanel({ candidates, onOpenDrawer }: Props) {
  if (candidates.length === 0) return null;

  const visible = candidates.slice(0, MAX_VISIBLE);
  const remaining = candidates.length - visible.length;

  return (
    <Card
      style={{
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 8,
      }}
      styles={{ body: { padding: '14px 16px' } }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <StarOutlined style={{ color: DARK_THEME.yellow, fontSize: 16 }} />
        <Typography.Text
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: DARK_THEME.textPrimary,
          }}
        >
          {candidates.length} кандидатов
        </Typography.Text>
      </div>

      {/* Mini-cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
        {visible.map((c) => (
          <div
            key={c.proposed_name}
            style={{
              background: DARK_THEME.darkAccent,
              border: `1px solid ${DARK_THEME.border}`,
              borderRadius: 6,
              padding: '8px 10px',
            }}
          >
            <Typography.Text
              style={{ fontWeight: 600, color: DARK_THEME.textPrimary, fontSize: 13, display: 'block' }}
            >
              {c.proposed_name}
            </Typography.Text>
            <Typography.Text
              style={{ fontSize: 12, color: DARK_THEME.textMuted, display: 'block', marginTop: 2 }}
            >
              {c.hours.toFixed(1)} ч · {c.issues_count} задач
            </Typography.Text>
            {c.sample_keys.length > 0 && (
              <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {c.sample_keys.slice(0, 5).map((k) => (
                  <Tag key={k} style={{ fontSize: 10, margin: 0, padding: '0 4px', lineHeight: '18px' }}>
                    {k}
                  </Tag>
                ))}
              </div>
            )}
          </div>
        ))}

        {remaining > 0 && (
          <Typography.Text
            style={{ fontSize: 12, color: DARK_THEME.textMuted, textAlign: 'center' }}
          >
            и ещё {remaining}{' '}
            <Typography.Link onClick={onOpenDrawer} style={{ fontSize: 12 }}>
              Просмотреть всех
            </Typography.Link>
          </Typography.Text>
        )}
      </div>

      <Button block type="primary" ghost onClick={onOpenDrawer}>
        Просмотреть всех кандидатов
      </Button>
    </Card>
  );
}
