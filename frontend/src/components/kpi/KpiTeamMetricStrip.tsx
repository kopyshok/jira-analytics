import { useMemo } from 'react';
import { Card, Typography } from 'antd';
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import type { KpiReportRow } from '../../api/kpi';

const { Text } = Typography;

interface MetricAverage {
  code: string;
  name: string;
  value: number | null;
  previous: number | null;
}

/** Среднее по метрике — только по людям с данными: «нет данных» не тянет вниз. */
function averages(rows: KpiReportRow[]): Map<string, { name: string; value: number | null }> {
  const acc = new Map<string, { name: string; values: number[] }>();
  for (const row of rows) {
    for (const m of row.metrics) {
      const entry = acc.get(m.code) ?? { name: m.name, values: [] };
      if (m.has_data && m.value != null) entry.values.push(m.value);
      acc.set(m.code, entry);
    }
  }
  const result = new Map<string, { name: string; value: number | null }>();
  for (const [code, entry] of acc) {
    result.set(code, {
      name: entry.name,
      value: entry.values.length ? entry.values.reduce((s, v) => s + v, 0) / entry.values.length : null,
    });
  }
  return result;
}

/**
 * Полоса метрик по выбранным командам: среднее, дельта к прошлому месяцу и
 * заметно ли метрика пустует. Отвечает на первый вопрос при открытии
 * страницы — «где просело», не заставляя читать таблицу по колонкам.
 */
export default function KpiTeamMetricStrip({
  rows, prevRows,
}: { rows: KpiReportRow[]; prevRows: KpiReportRow[] }) {
  const t = useThemeTokens();

  const metrics: MetricAverage[] = useMemo(() => {
    const current = averages(rows);
    const previous = averages(prevRows);
    return Array.from(current.entries()).map(([code, entry]) => ({
      code,
      name: entry.name,
      value: entry.value,
      previous: previous.get(code)?.value ?? null,
    }));
  }, [rows, prevRows]);

  if (metrics.length === 0) return null;

  return (
    <Card size="small" title="Метрики по выбранным командам" style={{ marginBottom: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(165px, 1fr))', gap: 10 }}>
        {metrics.map((m) => {
          const delta = m.value != null && m.previous != null ? m.value - m.previous : null;
          const empty = m.value == null;
          return (
            <div
              key={m.code}
              style={{
                padding: '9px 12px', borderRadius: 10, background: t.darkRows,
                opacity: empty ? 0.6 : 1, minWidth: 0,
              }}
            >
              <Text type="secondary" style={{ fontSize: 11, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {m.name}
              </Text>
              {empty ? (
                <Text type="secondary" italic style={{ fontSize: 12.5 }}>нет данных</Text>
              ) : (
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                  <b className="num" style={{ fontSize: 17 }}>{Math.round(m.value as number)}%</b>
                  {delta != null && Math.abs(delta) >= 0.5 && (
                    <span
                      className="num"
                      style={{ fontSize: 11, color: delta > 0 ? t.success : t.danger }}
                    >
                      {delta > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                      {Math.abs(delta).toFixed(0)}
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
