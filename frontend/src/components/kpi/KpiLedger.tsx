import { useMemo, useState, type CSSProperties } from 'react';
import { Table, Typography, Tag, Empty } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import type { KpiReportRow, KpiTeamSummaryRow } from '../../api/kpi';

const { Text } = Typography;

type Status = 'good' | 'warn' | 'bad' | 'none';

function statusOf(value: number | null, target: number | null, warnBand: number | null): Status {
  if (value == null || target == null) return 'none';
  if (value >= target) return 'good';
  const band = warnBand ?? 10;
  if (value >= target - band) return 'warn';
  return 'bad';
}

function withAlpha(color: string, pct: number): string {
  return `color-mix(in srgb, ${color} ${pct}%, transparent)`;
}

function fmtPct(v: number | null): string {
  return v == null ? '—' : `${Math.round(v)}%`;
}

interface Tokens {
  success: string;
  danger: string;
  amber: string;
  textMuted: string;
}

function cellStyle(status: Status, t: Tokens): CSSProperties {
  if (status === 'good') return { background: withAlpha(t.success, 14), color: t.success };
  if (status === 'warn') return { background: withAlpha(t.amber, 16), color: t.amber };
  if (status === 'bad') return { background: withAlpha(t.danger, 14), color: t.danger };
  return { color: t.textMuted };
}

interface TeamRow {
  key: string;
  isTeam: true;
  team: string;
  members: KpiReportRow[];
  children: KpiReportRow[];
}
type TreeRow = TeamRow | (KpiReportRow & { key: string });

function isTeamRow(r: TreeRow): r is TeamRow {
  return 'isTeam' in r;
}

/** Простое среднее по уже посчитанным на сервере процентам — только для витрины
 * строки команды в ведомости. Итог и дельта команды берутся напрямую из
 * `/kpi/teams-summary` (см. ниже), это среднее их не подменяет. */
function avgOf(values: (number | null | undefined)[]): number | null {
  const usable = values.filter((v): v is number => v != null);
  if (!usable.length) return null;
  return usable.reduce((a, b) => a + b, 0) / usable.length;
}

export interface KpiLedgerProps {
  rows: KpiReportRow[];
  teamsSummaryByTeam: Map<string, KpiTeamSummaryRow>;
  loading?: boolean;
  onOpenEmployee?: (row: KpiReportRow) => void;
  onOpenBreakdown?: (row: KpiReportRow, metricCode: string, metricName: string) => void;
}

export default function KpiLedger({
  rows, teamsSummaryByTeam, loading, onOpenEmployee, onOpenBreakdown,
}: KpiLedgerProps) {
  const t = useThemeTokens();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const metricColumns = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of rows) {
      for (const m of row.metrics) {
        if (!seen.has(m.code)) seen.set(m.code, m.name);
      }
    }
    return Array.from(seen.entries()).map(([code, name]) => ({ code, name }));
  }, [rows]);

  const tree: TeamRow[] = useMemo(() => {
    const buckets = new Map<string, KpiReportRow[]>();
    for (const row of rows) {
      const key = row.team ?? '__none__';
      const arr = buckets.get(key) ?? [];
      arr.push(row);
      buckets.set(key, arr);
    }
    const keys = Array.from(buckets.keys()).sort((a, b) => {
      if (a === '__none__') return 1;
      if (b === '__none__') return -1;
      return a.localeCompare(b, 'ru');
    });
    return keys.map((key) => {
      const members = buckets.get(key)!;
      return {
        key: `team:${key}`,
        isTeam: true,
        team: key === '__none__' ? 'Без команды' : key,
        members,
        children: members.map((m) => ({ ...m, key: `emp:${m.employee_id}` })),
      };
    });
  }, [rows]);

  const expandedRowKeys = useMemo(
    () => tree.filter((r) => !collapsed.has(r.key)).map((r) => r.key),
    [tree, collapsed],
  );

  const nameColumn = {
    title: 'Сотрудник',
    key: 'name',
    fixed: 'left' as const,
    width: 260,
    render: (_: unknown, r: TreeRow) => {
      if (isTeamRow(r)) {
        return (
          <span style={{ fontWeight: 700 }}>
            {r.team}
            <Text type="secondary" style={{ fontWeight: 400, marginLeft: 6, fontSize: 12 }}>
              · {r.members.length} чел.
            </Text>
          </span>
        );
      }
      return (
        <div style={{ paddingLeft: 16 }}>
          <button
            type="button"
            onClick={() => onOpenEmployee?.(r)}
            style={{
              background: 'none', border: 'none', padding: 0, font: 'inherit',
              color: 'inherit', cursor: onOpenEmployee ? 'pointer' : 'default', textAlign: 'left',
              fontWeight: 600,
            }}
          >
            {r.employee_name}
          </button>
          {r.profile_code && (
            <Tag style={{ marginLeft: 6, fontSize: 10 }}>{r.profile_code}</Tag>
          )}
        </div>
      );
    },
  };

  const metricCols = metricColumns.map((col) => ({
    title: col.name,
    key: col.code,
    width: 130,
    align: 'right' as const,
    render: (_: unknown, r: TreeRow) => {
      if (isTeamRow(r)) {
        const avg = avgOf(r.members.map((m) => m.metrics.find((mm) => mm.code === col.code)?.value));
        const target = r.members[0]?.target_pct ?? null;
        const band = r.members[0]?.warn_band_pct ?? null;
        const status = statusOf(avg, target, band);
        return (
          <span className="num" style={{ ...cellStyle(status, t), fontWeight: 700, padding: '2px 6px', borderRadius: 6 }}>
            {fmtPct(avg)}
          </span>
        );
      }
      const metric = r.metrics.find((m) => m.code === col.code);
      if (!metric || !metric.has_data) {
        return (
          <span className="num" style={{ color: t.textMuted, fontStyle: 'italic', fontSize: 12 }}>
            нет данных
          </span>
        );
      }
      const status = statusOf(metric.value, r.target_pct, r.warn_band_pct);
      const clickable = !!onOpenBreakdown;
      return (
        <span
          role={clickable ? 'button' : undefined}
          tabIndex={clickable ? 0 : undefined}
          onClick={() => onOpenBreakdown?.(r, metric.code, metric.name)}
          className="num"
          style={{
            ...cellStyle(status, t), fontWeight: 600, padding: '2px 6px', borderRadius: 6,
            cursor: clickable ? 'pointer' : 'default',
          }}
        >
          {fmtPct(metric.value)}
        </span>
      );
    },
  }));

  const totalColumn = {
    title: 'Итог',
    key: 'total',
    fixed: 'right' as const,
    width: 110,
    align: 'right' as const,
    render: (_: unknown, r: TreeRow) => {
      if (isTeamRow(r)) {
        const summary = teamsSummaryByTeam.get(r.team);
        const value = summary?.avg_total ?? null;
        const status = statusOf(value, r.members[0]?.target_pct ?? null, r.members[0]?.warn_band_pct ?? null);
        const delta = summary?.delta ?? null;
        return (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span className="num" style={{ ...cellStyle(status, t), fontWeight: 800, fontSize: 14, padding: '2px 6px', borderRadius: 6 }}>
              {fmtPct(value)}
            </span>
            {delta != null && (
              <span
                className="num"
                style={{
                  fontSize: 10.5, fontWeight: 700,
                  color: delta > 0.05 ? t.success : delta < -0.05 ? t.danger : t.textMuted,
                  display: 'flex', alignItems: 'center', gap: 2,
                }}
              >
                {delta > 0.05 ? <ArrowUpOutlined /> : delta < -0.05 ? <ArrowDownOutlined /> : <MinusOutlined />}
                {Math.abs(delta).toFixed(1)} п.п.
              </span>
            )}
          </div>
        );
      }
      const status = statusOf(r.total, r.target_pct, r.warn_band_pct);
      return (
        <span className="num" style={{ ...cellStyle(status, t), fontWeight: 800, fontSize: 14, padding: '2px 6px', borderRadius: 6 }}>
          {fmtPct(r.total)}
        </span>
      );
    },
  };

  const columns = [nameColumn, ...metricCols, totalColumn];

  if (!loading && rows.length === 0) {
    return <Empty description="Нет данных за выбранный период" style={{ padding: '32px 0' }} />;
  }

  return (
    <div style={{ overflowX: 'auto', maxWidth: '100%' }}>
      <Table
        dataSource={tree}
        rowKey="key"
        loading={loading}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        columns={columns as any}
        pagination={false}
        size="small"
        scroll={{ x: 'max-content' }}
        expandable={{
          expandedRowKeys,
          childrenColumnName: 'children',
          onExpand: (expand, record) => {
            const r = record as TreeRow;
            if (!isTeamRow(r)) return;
            setCollapsed((prev) => {
              const next = new Set(prev);
              if (expand) next.delete(r.key); else next.add(r.key);
              return next;
            });
          },
        }}
        onRow={(record: TreeRow) => (isTeamRow(record)
          ? { onClick: () => setCollapsed((prev) => {
              const next = new Set(prev);
              if (next.has(record.key)) next.delete(record.key); else next.add(record.key);
              return next;
            }), style: { cursor: 'pointer' } }
          : {})}
      />
    </div>
  );
}
