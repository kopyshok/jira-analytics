import { useMemo, useState, type CSSProperties } from 'react';
import { Table, Typography, Tag, Empty, Alert, Button, Tooltip } from 'antd';
import {
  ArrowUpOutlined, ArrowDownOutlined, MinusOutlined,
  CheckCircleFilled, WarningFilled, CloseCircleFilled,
} from '@ant-design/icons';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import type { KpiReportRow, KpiTeamSummaryRow } from '../../api/kpi';
import { kpiStatusOf, onKpiCellActivate, type KpiStatus } from '../../utils/kpiShared';

const { Text } = Typography;

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

function cellStyle(status: KpiStatus, t: Tokens): CSSProperties {
  if (status === 'good') return { background: withAlpha(t.success, 14), color: t.success };
  if (status === 'warn') return { background: withAlpha(t.amber, 16), color: t.amber };
  if (status === 'bad') return { background: withAlpha(t.danger, 14), color: t.danger };
  return { color: t.textMuted };
}

/** Значок статуса рядом с числом — цвет ячейки не единственный сигнал,
 * иначе человек с нарушением цветовосприятия не отличит «на цели» от
 * «ниже цели» (дельта команды уже подстрахована стрелкой, метрикам нужно то
 * же, см. ревью, мелочи). */
function StatusIcon({ status }: { status: KpiStatus }) {
  if (status === 'good') return <CheckCircleFilled style={{ fontSize: 10 }} />;
  if (status === 'warn') return <WarningFilled style={{ fontSize: 10 }} />;
  if (status === 'bad') return <CloseCircleFilled style={{ fontSize: 10 }} />;
  return null;
}

const LEGEND_ITEMS: { status: KpiStatus; label: string }[] = [
  { status: 'good', label: 'На цели' },
  { status: 'warn', label: 'Жёлтая зона' },
  { status: 'bad', label: 'Ниже цели' },
];

/** Легенда цветовой индикации ведомости — из макета, раньше не была перенесена. */
export function KpiStatusLegend() {
  const t = useThemeTokens();
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 11.5, color: t.textMuted }}>
      {LEGEND_ITEMS.map((it) => (
        <span key={it.status} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ ...cellStyle(it.status, t), display: 'inline-flex', padding: '1px 5px', borderRadius: 5 }}>
            <StatusIcon status={it.status} />
          </span>
          {it.label}
        </span>
      ))}
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <Text type="secondary" style={{ fontStyle: 'italic', fontSize: 11 }}>нет данных</Text>
        — метрика не участвует в расчёте
      </span>
    </div>
  );
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

export interface KpiSelectedCell {
  employeeId: string;
  metricCode: string;
}

export interface KpiLedgerProps {
  rows: KpiReportRow[];
  teamsSummaryByTeam: Map<string, KpiTeamSummaryRow>;
  loading?: boolean;
  /** Ошибка запроса отчёта — руководитель не должен принять её за «месяц
   * пустой» (см. ревью, ВАЖНО 6). */
  error?: Error | null;
  onRetry?: () => void;
  onOpenEmployee?: (row: KpiReportRow) => void;
  onOpenBreakdown?: (row: KpiReportRow, metricCode: string, metricName: string) => void;
  /** Ячейка, раскрытая в панели расчёта снизу — подсвечивается рамкой. */
  selectedCell?: KpiSelectedCell | null;
  /** Итоги прошлого месяца по сотруднику — для дельты в строке человека. */
  prevTotals?: Map<string, number>;
}

export default function KpiLedger({
  rows, teamsSummaryByTeam, loading, error, onRetry, onOpenEmployee, onOpenBreakdown,
  selectedCell, prevTotals,
}: KpiLedgerProps) {
  const t = useThemeTokens();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  // Ранг внутри команды: место человека в своей команде по итогу. Смотреть
  // «кто где» по отсортированному списку из трёх десятков строк неудобно.
  const rankByEmployee = useMemo(() => {
    const byTeam = new Map<string, KpiReportRow[]>();
    for (const row of rows) {
      const key = row.team ?? '__none__';
      byTeam.set(key, [...(byTeam.get(key) ?? []), row]);
    }
    const result = new Map<string, number>();
    for (const members of byTeam.values()) {
      members
        .filter((m) => m.total != null)
        .sort((a, b) => (b.total ?? 0) - (a.total ?? 0))
        .forEach((m, i) => result.set(m.employee_id, i + 1));
    }
    return result;
  }, [rows]);

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

  // Колонки пересчитываются, только когда реально меняются входные данные —
  // раньше объект колонок пересоздавался на каждую отрисовку (включая
  // сворачивание одной команды, которое трогает только `collapsed`), из-за
  // чего таблица теряла возможность переиспользовать неизменившиеся ячейки
  // (см. ревью, мелочи).
  const columns = useMemo(() => {
    const rankColumn = {
      title: '#',
      key: 'rank',
      fixed: 'left' as const,
      width: 44,
      align: 'right' as const,
      render: (_: unknown, r: TreeRow) => {
        if (isTeamRow(r)) return null;
        const rank = rankByEmployee.get(r.employee_id);
        return (
          <span className="num" style={{ color: t.textMuted, fontSize: 11.5 }}>{rank ?? '—'}</span>
        );
      },
    };

    const nameColumn = {
      title: 'Сотрудник',
      key: 'name',
      fixed: 'left' as const,
      width: 260,
      render: (_: unknown, r: TreeRow) => {
        if (isTeamRow(r)) {
          const memberCount = teamsSummaryByTeam.get(r.team)?.member_count ?? r.members.length;
          return (
            <span style={{ fontWeight: 700 }}>
              {r.team}
              <Text type="secondary" style={{ fontWeight: 400, marginLeft: 6, fontSize: 12 }}>
                · {memberCount} чел.
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
            {r.profile_name && (
              <Tag style={{ marginLeft: 6, fontSize: 10 }}>{r.profile_name}</Tag>
            )}
          </div>
        );
      },
    };

    const metricCols = metricColumns.map((col) => ({
      // Полное название — в подсказке, в шапке колонки — короткая версия
      // (обрезка с многоточием), иначе длинные названия метрик из
      // справочника растягивают таблицу (см. «из макета не перенесено»).
      title: (
        <Tooltip title={col.name}>
          <span style={{
            display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
          >
            {col.name}
          </span>
        </Tooltip>
      ),
      key: col.code,
      width: 130,
      align: 'right' as const,
      render: (_: unknown, r: TreeRow) => {
        if (isTeamRow(r)) {
          // Среднее по метрике, цель и жёлтая зона строки команды приходят
          // готовыми с сервера (`/kpi/teams-summary`) — тем же расчётом, что и
          // итог, а не пересчитываются на клиенте простым средним по первому
          // сотруднику (см. ревью, ВАЖНО 5).
          const summary = teamsSummaryByTeam.get(r.team);
          const metric = summary?.metrics.find((mm) => mm.code === col.code);
          const value = metric?.has_data ? metric.value : null;
          const status = kpiStatusOf(value, summary?.target_pct ?? null, summary?.warn_band_pct ?? null);
          return (
            <span className="num" style={{ ...cellStyle(status, t), fontWeight: 700, padding: '2px 6px', borderRadius: 6, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <StatusIcon status={status} />
              {fmtPct(value)}
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
        const status = kpiStatusOf(metric.value, r.target_pct, r.warn_band_pct);
        const clickable = !!onOpenBreakdown;
        const activate = () => onOpenBreakdown?.(r, metric.code, metric.name);
        const selected = selectedCell?.employeeId === r.employee_id
          && selectedCell?.metricCode === metric.code;
        return (
          <span
            role={clickable ? 'button' : undefined}
            tabIndex={clickable ? 0 : undefined}
            onClick={activate}
            onKeyDown={clickable ? onKpiCellActivate(activate) : undefined}
            className="num"
            style={{
              ...cellStyle(status, t), fontWeight: 600, padding: '2px 6px', borderRadius: 6,
              cursor: clickable ? 'pointer' : 'default', display: 'inline-flex', alignItems: 'center', gap: 4,
              // Раскрытая в панели снизу ячейка отмечена рамкой — иначе при
              // переборе соседних ячеек непонятно, чей расчёт сейчас внизу.
              outline: selected ? `2px solid ${t.cyanPrimary}` : undefined,
              outlineOffset: selected ? 1 : undefined,
            }}
          >
            <StatusIcon status={status} />
            {fmtPct(metric.value)}
          </span>
        );
      },
    }));

    const totalColumn = {
      title: 'Итог',
      key: 'total',
      fixed: 'right' as const,
      width: 190,
      align: 'right' as const,
      render: (_: unknown, r: TreeRow) => {
        if (isTeamRow(r)) {
          const summary = teamsSummaryByTeam.get(r.team);
          const value = summary?.avg_total ?? null;
          const status = kpiStatusOf(value, summary?.target_pct ?? null, summary?.warn_band_pct ?? null);
          const delta = summary?.delta ?? null;
          return (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
              <span className="num" style={{ ...cellStyle(status, t), fontWeight: 800, fontSize: 14, padding: '2px 6px', borderRadius: 6, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <StatusIcon status={status} />
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
        const status = kpiStatusOf(r.total, r.target_pct, r.warn_band_pct);
        const prev = prevTotals?.get(r.employee_id);
        const delta = prev != null && r.total != null ? r.total - prev : null;
        return (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
            {delta != null && Math.abs(delta) >= 0.05 && (
              <span
                className="num"
                style={{
                  fontSize: 10.5, fontWeight: 700,
                  color: delta > 0 ? t.success : t.danger,
                  display: 'flex', alignItems: 'center', gap: 1,
                }}
              >
                {delta > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                {Math.abs(delta).toFixed(1)}
              </span>
            )}
            {/* Полоска рядом с числом: разницу между 86% и 98% глаз ловит
                быстрее по длине, чем по цифрам. */}
            <span style={{
              width: 54, height: 5, borderRadius: 3, background: t.darkRows, overflow: 'hidden',
              display: 'inline-block',
            }}
            >
              <span style={{
                display: 'block', height: '100%',
                width: `${Math.min(100, Math.max(0, r.total ?? 0))}%`,
                background: cellStyle(status, t).color as string,
              }}
              />
            </span>
            <span className="num" style={{ ...cellStyle(status, t), fontWeight: 800, fontSize: 14, padding: '2px 6px', borderRadius: 6, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <StatusIcon status={status} />
              {fmtPct(r.total)}
            </span>
          </div>
        );
      },
    };

    return [rankColumn, nameColumn, ...metricCols, totalColumn];
  }, [metricColumns, teamsSummaryByTeam, t, onOpenEmployee, onOpenBreakdown, rankByEmployee,
    selectedCell, prevTotals]);

  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        title="Не удалось загрузить ведомость"
        description={error.message}
        action={onRetry && <Button size="small" onClick={onRetry}>Повторить</Button>}
        style={{ margin: '16px 0' }}
      />
    );
  }

  if (!loading && rows.length === 0) {
    return <Empty description="Нет данных за выбранный период" style={{ padding: '32px 0' }} />;
  }

  return (
    <Table
      dataSource={tree}
      rowKey="key"
      loading={loading}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      columns={columns as any}
      pagination={false}
      size="small"
      // Прокрутка — только внутренняя (у таблицы своя), без внешней
      // обёртки: лишняя внешняя прокрутка ломала стики-поведение
      // зафиксированных колонок (см. ревью, мелочи). Закреплённая шапка —
      // из макета, раньше не была перенесена.
      scroll={{ x: 'max-content' }}
      sticky
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
  );
}
