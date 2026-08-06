import { useMemo } from 'react';
import { Card, Empty, Typography } from 'antd';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import type { KpiReportRow } from '../../api/kpi';
import { kpiStatusOf } from '../../utils/kpiShared';

const { Text } = Typography;

const BUCKETS = [
  { label: '<60', from: -Infinity, to: 60 },
  { label: '60–70', from: 60, to: 70 },
  { label: '70–80', from: 70, to: 80 },
  { label: '80–90', from: 80, to: 90 },
  { label: '90–95', from: 90, to: 95 },
  { label: '95–100', from: 95, to: Infinity },
];

/**
 * Распределение людей по итогу. Средний КЭ 96% может означать и «все ровно», и
 * «пятеро отличников и один провал» — гистограмма отличает одно от другого за
 * один взгляд, чего ведомость не делает.
 */
export default function KpiDistribution({ rows }: { rows: KpiReportRow[] }) {
  const t = useThemeTokens();

  const { counts, max, target } = useMemo(() => {
    const c = BUCKETS.map(() => 0);
    const totals = rows.map((r) => r.total).filter((v): v is number => v != null);
    for (const v of totals) {
      const i = BUCKETS.findIndex((b) => v >= b.from && v < b.to);
      if (i >= 0) c[i] += 1;
    }
    const targets = new Set(rows.map((r) => r.target_pct).filter((v): v is number => v != null));
    return {
      counts: c,
      max: Math.max(1, ...c),
      target: targets.size === 1 ? [...targets][0] : null,
    };
  }, [rows]);

  const hasData = counts.some((c) => c > 0);

  return (
    <Card size="small" title="Распределение по итогу">
      {!hasData ? (
        <Empty description="Нет посчитанных итогов" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 130 }}>
            {BUCKETS.map((b, i) => {
              // Цвет столбца — по тому же правилу, что и ячейки ведомости:
              // диапазон окрашен как значение в его середине.
              const mid = b.to === Infinity ? 97.5 : b.from === -Infinity ? 50 : (b.from + b.to) / 2;
              const status = kpiStatusOf(mid, target, 10);
              const color = status === 'good' ? t.success : status === 'warn' ? t.amber : t.danger;
              return (
                <div key={b.label} style={{ flex: 1, textAlign: 'center', minWidth: 0 }}>
                  <div className="num" style={{ fontSize: 11, color: t.textMuted, marginBottom: 3 }}>
                    {counts[i] || ''}
                  </div>
                  <div
                    style={{
                      height: `${Math.max(4, (counts[i] / max) * 88)}px`,
                      background: color, opacity: counts[i] ? 0.9 : 0.25,
                      borderRadius: 4,
                    }}
                  />
                  <div style={{ fontSize: 10, color: t.textMuted, marginTop: 5 }}>{b.label}</div>
                </div>
              );
            })}
          </div>
          <Text type="secondary" style={{ fontSize: 11.5, display: 'block', marginTop: 10 }}>
            {target != null
              ? `Цель ${target}%. Ниже цели — ${rows.filter((r) => r.total != null && r.total < target).length} чел.`
              : 'У сотрудников разные цели — граница на графике не показана.'}
          </Text>
        </>
      )}
    </Card>
  );
}
