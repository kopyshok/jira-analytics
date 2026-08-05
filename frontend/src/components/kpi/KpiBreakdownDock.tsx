import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert, Button, Collapse, Empty, Segmented, Spin, Table, Tag, Tooltip, Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CloseOutlined, LinkOutlined } from '@ant-design/icons';
import KpiFunnel from './KpiFunnel';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import {
  fetchBreakdown,
  type KpiBreakdownTable, type KpiReportRow, type KpiTableDropped, type KpiTableRow,
} from '../../api/kpi';
import { KPI_MONTH_ABBR_RU } from '../../utils/kpiShared';

const { Text } = Typography;

export interface KpiBreakdownTarget {
  row: KpiReportRow;
  metricCode: string;
  metricName: string;
}

export interface KpiBreakdownDockProps {
  target: KpiBreakdownTarget | null;
  year: number;
  month: number;
  direction?: string;
  /** Команды, с которыми запрошен отчёт (глобальный фильтр) — расшифровка
   * использует тот же отбор, что и ведомость, иначе дробь под метрикой может
   * не сойтись с числами отчёта (см. ревью, BLOCKER 3). */
  teams?: string;
  onClose: () => void;
}

/** Дата задачи/записи коротко — таблица разбора живёт внутри одного месяца. */
function shortDay(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** Задержка внесения часов словами: сутки читаются лучше, чем «528 ч». */
function delayText(hours?: number | null): string {
  if (hours == null) return '—';
  if (hours < 24) return `${Math.round(hours)} ч`;
  return `${Math.round(hours / 24)} дн`;
}

function IssueKey({ row }: { row: KpiTableRow | KpiTableDropped }) {
  if (!row.key) return <span>—</span>;
  return row.url ? (
    <a
      href={row.url}
      target="_blank"
      rel="noreferrer"
      className="num"
      style={{ fontWeight: 700, whiteSpace: 'nowrap' }}
    >
      {row.key} <LinkOutlined style={{ fontSize: 10 }} />
    </a>
  ) : (
    <span className="num" style={{ fontWeight: 700 }}>{row.key}</span>
  );
}

/**
 * Итог по строке словами. Формулировка зависит от того, что метрика считает
 * числителем: у метрики качества туда попадают баги, поэтому «засчитана» там
 * означало бы ровно обратное смыслу.
 */
function Verdict({ table, row }: { table: KpiBreakdownTable; row: KpiTableRow }) {
  const reasons = row.reasons.join(' · ');
  const tag = (() => {
    if (table.kind === 'worklogs') {
      return row.problem
        ? <Tag color="error">просрочено · {delayText(row.delay_hours)}</Tag>
        : <Tag color="success">вовремя</Tag>;
    }
    if (table.kind === 'norm') {
      if (!row.counted) return <Tag color="warning">нет данных</Tag>;
      return row.problem
        ? <Tag color="error">превышение {row.deviation_pct}%</Tag>
        : <Tag color="success">в норме</Tag>;
    }
    if (table.kind === 'score') {
      if (!row.counted) return <Tag color="warning">нет оценки</Tag>;
      return row.problem
        ? <Tag color="warning">{row.score_pct}% от максимума</Tag>
        : <Tag color="success">максимум</Tag>;
    }
    if (table.invert) {
      return row.problem
        ? <Tag color="error">нарушение</Tag>
        : <Tag>без нарушений</Tag>;
    }
    return row.counted
      ? <Tag color="success">засчитана</Tag>
      : <Tag color="error">не засчитана</Tag>;
  })();
  return reasons ? <Tooltip title={reasons}>{tag}</Tooltip> : tag;
}

/** Колонки таблицы разбора — по способу расчёта метрики. */
function useColumns(table: KpiBreakdownTable, good: string, bad: string): ColumnsType<KpiTableRow> {
  return useMemo(() => {
    const head: ColumnsType<KpiTableRow> = [
      {
        title: 'Ключ', dataIndex: 'key', width: 120, fixed: 'left',
        render: (_v, row) => (
          <span>
            <IssueKey row={row} />
            {row.outside_base && (
              <Tooltip title="Учтена показателем, хотя её нет в списке сравнения">
                <Tag style={{ marginInlineStart: 6 }}>сверх списка</Tag>
              </Tooltip>
            )}
          </span>
        ),
      },
      { title: 'Задача', dataIndex: 'summary', ellipsis: true, render: (v) => v || '—' },
    ];

    if (table.kind === 'worklogs') {
      return [
        ...head,
        {
          title: 'Дата работы', dataIndex: 'started_at', width: 110,
          render: (v) => <span className="num">{shortDay(v)}</span>,
        },
        {
          title: 'Внесено', dataIndex: 'created_at', width: 100,
          render: (v) => <span className="num">{shortDay(v)}</span>,
        },
        {
          title: 'Часы', dataIndex: 'hours', width: 80, align: 'right',
          render: (v) => <span className="num">{v}</span>,
        },
        {
          title: 'Итог', width: 190,
          render: (_v, row) => <Verdict table={table} row={row} />,
        },
      ];
    }

    const closed: ColumnsType<KpiTableRow> = [{
      title: 'Закрыта', dataIndex: 'resolved_at', width: 100,
      render: (v) => <span className="num">{shortDay(v)}</span>,
    }];

    if (table.kind === 'norm') {
      return [
        ...head, ...closed,
        {
          title: 'Факт', dataIndex: 'fact', width: 90, align: 'right',
          render: (v) => <span className="num">{v == null ? '—' : `${v} дн`}</span>,
        },
        {
          title: 'Норматив', width: 100, align: 'right',
          render: () => (
            <span className="num">
              {table.norm_value == null ? '—' : `${table.norm_value} дн`}
            </span>
          ),
        },
        {
          title: 'Отклонение', dataIndex: 'deviation_pct', width: 120, align: 'right',
          render: (v: number | null, row) => (
            <span className="num" style={{ color: row.problem ? bad : good }}>
              {v == null ? '—' : `${v > 0 ? '+' : ''}${v}%`}
            </span>
          ),
        },
        { title: 'Итог', width: 180, render: (_v, row) => <Verdict table={table} row={row} /> },
      ];
    }

    if (table.kind === 'score') {
      return [
        ...head, ...closed,
        {
          title: 'Оценка', dataIndex: 'score', width: 100, align: 'right',
          render: (v) => (
            <span className="num">
              {v == null ? '—' : `${v} из ${table.score_max ?? 5}`}
            </span>
          ),
        },
        { title: 'Итог', width: 190, render: (_v, row) => <Verdict table={table} row={row} /> },
      ];
    }

    return [
      ...head, ...closed,
      ...table.checks.map((check) => ({
        title: check.label,
        width: 150,
        align: 'center' as const,
        render: (_v: unknown, row: KpiTableRow) => {
          const ok = row.checks?.[check.code];
          return (
            <span style={{ color: ok ? good : bad, fontWeight: 600, fontSize: 12 }}>
              {ok ? '✓ есть' : '✕ нет'}
            </span>
          );
        },
      })),
      { title: 'Итог', width: 150, render: (_v, row) => <Verdict table={table} row={row} /> },
    ];
  }, [table, good, bad]);
}

/**
 * Расчёт показателя — панелью под ведомостью, а не модальным окном.
 *
 * Главное здесь — таблица разбора: строка на задачу, колонка на требование
 * метрики, проблемные строки подсвечены. Раньше панель показывала два списка
 * («что считаем» и «с чем сравниваем»), и найти незачтённую задачу можно было
 * только сверив их глазами. Воронка отбора осталась, но убрана в свёрнутый
 * блок: она отвечает на вопрос «почему задач столько», а не «что не так с
 * этой задачей».
 */
export default function KpiBreakdownDock({
  target, year, month, direction, teams, onClose,
}: KpiBreakdownDockProps) {
  const t = useThemeTokens();
  const [onlyProblem, setOnlyProblem] = useState(false);

  const query = useQuery({
    queryKey: [
      'kpi', 'breakdown', target?.row.account_id, target?.metricCode, year, month, teams, direction,
    ],
    queryFn: ({ signal }) => fetchBreakdown(
      {
        account_id: target!.row.account_id, metric_code: target!.metricCode, year, month,
        teams, direction,
      },
      signal,
    ),
    enabled: !!target,
  });

  const table = query.data?.table;
  const columns = useColumns(
    table ?? { kind: 'checks', checks: [], rows: [], total_count: 0, counted_count: 0,
      problem_count: 0, truncated: false, dropped: [] },
    t.success,
    t.danger,
  );
  const rows = useMemo(
    () => (onlyProblem ? (table?.rows ?? []).filter((r) => r.problem) : table?.rows ?? []),
    [table, onlyProblem],
  );

  if (!target) return null;

  const metric = target.row.metrics.find((m) => m.code === target.metricCode);
  const problemLabel = table?.invert || table?.kind === 'worklogs' ? 'Нарушения' : 'С ошибкой';
  const okLabel = table?.kind === 'worklogs' ? 'вовремя' : 'засчитано';

  return (
    <section
      aria-label={`Расчёт показателя «${target.metricName}»`}
      style={{
        marginTop: 14, borderRadius: 14, overflow: 'hidden',
        border: `1px solid ${t.border}`, borderTop: `2px solid ${t.cyanPrimary}`,
        background: t.darkAccent,
      }}
    >
      <header
        style={{
          display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
          padding: '12px 16px', borderBottom: `1px solid ${t.border}`,
        }}
      >
        <div className="num" style={{ fontSize: 24, fontWeight: 800 }}>
          {/* Дробь берётся из тех же чисел, что и списки задач ниже, а не из
              значения метрики в отчёте — иначе для «норматив к факту» и
              «балл к максимуму» она показывала бы норматив/балл, а не число
              задач под ней (см. BLOCKER 2 ревью). */}
          {query.data?.numerator_count ?? '—'}
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 500, margin: '0 6px' }}>из</Text>
          {query.data?.denominator_count ?? '—'}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600 }}>
            {target.metricName} · {target.row.employee_name}
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {KPI_MONTH_ABBR_RU[month - 1]} {year}
            {target.row.team ? ` · ${target.row.team}` : ' · без команды'}
            {metric ? ` · вес ${Math.round(metric.weight * 100)}%` : ''}
            {target.row.target_pct != null ? ` · цель ${target.row.target_pct}%` : ''}
          </Text>
        </div>
        <span className="num" style={{ fontSize: 15, fontWeight: 700 }}>
          {metric?.has_data ? `${Math.round(metric.value ?? 0)}%` : 'нет данных'}
        </span>
        <Button
          size="small" type="text" icon={<CloseOutlined />} onClick={onClose}
          style={{ marginInlineStart: 'auto' }}
        >
          Свернуть
        </Button>
      </header>

      {query.isLoading ? (
        <div style={{ display: 'grid', placeItems: 'center', minHeight: 140 }}><Spin /></div>
      ) : query.isError ? (
        <div style={{ padding: 16 }}>
          <Alert
            type="error"
            showIcon
            title="Не удалось загрузить расчёт"
            description={(query.error as Error).message}
            action={<Button size="small" onClick={() => query.refetch()}>Повторить</Button>}
          />
        </div>
      ) : !table || table.total_count === 0 ? (
        <Empty
          description="За этот месяц у сотрудника нет строк для разбора"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ margin: '20px 0' }}
        />
      ) : (
        <>
          <div
            style={{
              display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
              padding: '10px 16px', borderBottom: `1px solid ${t.border}`,
            }}
          >
            <Segmented
              size="small"
              value={onlyProblem ? 'problem' : 'all'}
              onChange={(v) => setOnlyProblem(v === 'problem')}
              options={[
                { label: `Все · ${table.total_count}`, value: 'all' },
                { label: `${problemLabel} · ${table.problem_count}`, value: 'problem' },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {table.counted_count} {okLabel}
              {table.problem_count > 0 ? ` · ${table.problem_count} требуют внимания` : ''}
              {table.truncated ? ` · показаны первые ${table.rows.length}` : ''}
            </Text>
          </div>

          <Table<KpiTableRow>
            size="small"
            columns={columns}
            dataSource={rows}
            rowKey="id"
            pagination={rows.length > 25 ? { pageSize: 25, size: 'small' } : false}
            scroll={{ x: 'max-content' }}
            onRow={(row) => ({
              style: row.problem
                ? {
                  background: `color-mix(in srgb, ${t.danger} 12%, transparent)`,
                  boxShadow: `inset 3px 0 0 ${t.danger}`,
                }
                : undefined,
            })}
            locale={{ emptyText: 'Строк с ошибками нет' }}
          />

          <Collapse
            ghost
            size="small"
            items={[
              ...(table.dropped.length > 0 ? [{
                key: 'dropped',
                label: `${table.kind === 'worklogs' ? 'Не судим' : 'Отсеяно до сравнения'} · ${table.dropped.length}`,
                children: (
                  <Table<KpiTableDropped>
                    size="small"
                    pagination={table.dropped.length > 10 ? { pageSize: 10, size: 'small' } : false}
                    rowKey="id"
                    scroll={{ x: 'max-content' }}
                    dataSource={table.dropped}
                    columns={[
                      { title: 'Ключ', width: 120, render: (_v, row) => <IssueKey row={row} /> },
                      { title: 'Задача', dataIndex: 'summary', ellipsis: true, render: (v) => v || '—' },
                      {
                        title: table.kind === 'worklogs' ? 'Дата работы' : 'Закрыта',
                        width: 110,
                        render: (_v, row) => (
                          <span className="num">
                            {shortDay(row.started_at ?? row.resolved_at)}
                          </span>
                        ),
                      },
                      {
                        title: 'Почему не вошла', dataIndex: 'reason', width: 230,
                        render: (v: string) => <Tag color="warning">{v}</Tag>,
                      },
                    ]}
                  />
                ),
              }] : []),
              {
                key: 'funnel',
                label: 'Как получилось это число — отбор по шагам',
                children: (
                  <div
                    style={{
                      display: 'grid', gap: 14,
                      gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))',
                    }}
                  >
                    <KpiFunnel steps={query.data?.numerator_funnel ?? []} title="Что считаем" />
                    {(query.data?.denominator_funnel.length ?? 0) > 0 && (
                      <KpiFunnel
                        steps={query.data?.denominator_funnel ?? []}
                        title="С чем сравниваем"
                      />
                    )}
                  </div>
                ),
              },
            ]}
          />
        </>
      )}
    </section>
  );
}
