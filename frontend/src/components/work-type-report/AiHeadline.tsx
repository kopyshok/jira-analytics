import { Card, Tag } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { WorkTypeReportResponse } from '../../types/workTypeReport';

interface Props {
  report: WorkTypeReportResponse;
}

export default function AiHeadline({ report }: Props) {
  const { data, model_id, prompt_version } = report;
  const totals = data.totals;
  const headline = data.headline;
  const isFallback = data.is_fallback_narrative;

  return (
    <Card
      size="small"
      style={{
        borderLeft: `4px solid ${DARK_THEME.cyanPrimary}`,
        border: `1px solid ${DARK_THEME.border}`,
        background: `linear-gradient(135deg, ${DARK_THEME.cardBg} 0%, ${DARK_THEME.darkAccent} 100%)`,
        marginBottom: 16,
      }}
      styles={{ body: { padding: '14px 16px' } }}
    >
      {/* Headline */}
      <div
        style={{
          fontSize: 15,
          fontWeight: 600,
          color: headline ? DARK_THEME.textPrimary : DARK_THEME.textMuted,
          marginBottom: 8,
          lineHeight: 1.4,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
        title={headline || undefined}
      >
        {headline || '«AI-сводка появится после первого расчёта»'}
      </div>

      {/* Meta row */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          alignItems: 'center',
          fontSize: 11,
          color: DARK_THEME.textMuted,
        }}
      >
        {model_id && <span>Модель: {model_id}</span>}
        <span>
          {totals.tasks.toLocaleString('ru')} задач, {Math.round(totals.hours).toLocaleString('ru')} ч
        </span>
        {prompt_version && <span>Промпт v{prompt_version}</span>}
        <Tag
          color={isFallback ? 'gold' : 'green'}
          style={{ marginInlineEnd: 0, fontSize: 11 }}
        >
          {isFallback ? 'fallback' : 'high'}
        </Tag>
        {isFallback && (
          <span style={{ color: DARK_THEME.amber, fontSize: 11 }}>
            Нарратив построен по шаблону — AI-анализ недоступен
          </span>
        )}
      </div>
    </Card>
  );
}
