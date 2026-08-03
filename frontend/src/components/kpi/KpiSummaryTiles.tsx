import { Typography } from 'antd';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import type { KpiReportSummary } from '../../api/kpi';

const { Text } = Typography;

interface TileProps {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
}

function Tile({ label, value, hint, accent }: TileProps) {
  const t = useThemeTokens();
  return (
    <div
      style={{
        background: t.darkAccent, border: `1px solid ${t.border}`, borderRadius: 12,
        padding: '12px 15px', minWidth: 0,
      }}
    >
      <Text type="secondary" style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 700 }}>
        {label}
      </Text>
      <div className="num" style={{ fontSize: 24, fontWeight: 600, marginTop: 2, color: accent }}>
        {value}
      </div>
      {hint && (
        <Text type="secondary" style={{ fontSize: 11.5, display: 'block', marginTop: 2 }}>{hint}</Text>
      )}
    </div>
  );
}

export interface KpiSummaryTilesProps {
  summary?: KpiReportSummary;
  peopleCount: number;
  /** Сколько человек команды не оценивается — их роль не привязана к профилю. */
  skippedNoProfile: number;
}

/**
 * Полоса итогов раздела. Четвёртая плитка — покрытие профилями: без неё
 * исчезновение человека из ведомости выглядит как пропажа данных, а не как
 * следствие незаполненной роли.
 */
export default function KpiSummaryTiles({ summary, peopleCount, skippedNoProfile }: KpiSummaryTilesProps) {
  const t = useThemeTokens();
  const evaluated = peopleCount;
  const total = peopleCount + skippedNoProfile;

  return (
    <div
      style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
        gap: 12, marginBottom: 14,
      }}
    >
      <Tile
        label="Средний КЭ"
        value={summary?.avg_total != null ? `${Math.round(summary.avg_total)}%` : '—'}
        hint="по оценённым сотрудникам"
      />
      <Tile
        label="Ниже цели"
        value={summary ? String(summary.below_target_count) : '—'}
        hint={`из ${peopleCount} человек`}
        accent={summary && summary.below_target_count > 0 ? t.danger : undefined}
      />
      <Tile
        label="Метрик без данных"
        value={summary ? String(summary.no_data_metrics_count) : '—'}
        hint={summary?.no_data_by_metric.length
          ? `${summary.no_data_by_metric.length} метрик пустуют` : 'все метрики посчитаны'}
        accent={summary && summary.no_data_metrics_count > 0 ? t.amber : undefined}
      />
      <Tile
        label="Покрытие профилями"
        value={`${evaluated} из ${total}`}
        hint={skippedNoProfile > 0
          ? `${skippedNoProfile} чел. без профиля оценки`
          : 'все роли привязаны к профилю'}
        accent={skippedNoProfile > 0 ? t.amber : undefined}
      />
    </div>
  );
}
