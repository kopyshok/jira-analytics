import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Empty, Spin, Tag, Typography } from 'antd';
import { CloseOutlined, LinkOutlined } from '@ant-design/icons';
import KpiFunnel from './KpiFunnel';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import {
  fetchBreakdown, isWorklogItem, type KpiBreakdownItem, type KpiReportRow,
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

// У одной задачи может быть несколько списаний трудозатрат — ключевать список
// по идентификатору записи о трудозатратах, а не по задаче, иначе React
// получает повторяющиеся ключи (см. ревью, находка 3).
function itemKey(item: KpiBreakdownItem): string {
  return isWorklogItem(item) ? item.id : item.key;
}

function ItemRow({ item }: { item: KpiBreakdownItem }) {
  const worklog = isWorklogItem(item);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', minWidth: 0 }}>
      {item.key && (
        item.url ? (
          <a href={item.url} target="_blank" rel="noreferrer" className="num" style={{ fontSize: 12, fontWeight: 700, flex: '0 0 auto' }}>
            {item.key} <LinkOutlined style={{ fontSize: 10 }} />
          </a>
        ) : (
          <span className="num" style={{ fontSize: 12, fontWeight: 700, flex: '0 0 auto' }}>{item.key}</span>
        )
      )}
      <span style={{
        flex: '1 1 auto', minWidth: 0, fontSize: 12.5, overflow: 'hidden',
        textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}
      >
        {item.summary ?? '—'}
      </span>
      {worklog ? (
        <Tag color={item.late ? 'error' : 'success'} style={{ margin: 0, flex: '0 0 auto' }}>
          {item.late ? 'просрочено' : 'вовремя'} · {item.hours}ч
        </Tag>
      ) : (
        <>
          {item.fact != null && (
            <Tag className="num" style={{ margin: 0, flex: '0 0 auto' }}>факт {item.fact}</Tag>
          )}
          {item.score != null && (
            <Tag className="num" style={{ margin: 0, flex: '0 0 auto' }}>балл {item.score}</Tag>
          )}
          <Tag style={{ margin: 0, flex: '0 0 auto' }}>{item.resolution ?? item.status ?? '—'}</Tag>
        </>
      )}
    </div>
  );
}

/** Список задач расшифровки — простая разметка вместо AntD List: в шестой
 *  версии он объявлен устаревшим и печатает предупреждение в консоль. */
function ItemList({ items, borderColor }: { items: KpiBreakdownItem[]; borderColor: string }) {
  return (
    <div role="list">
      {items.map((item, i) => (
        <div
          key={itemKey(item)}
          role="listitem"
          style={{ padding: '7px 4px', borderTop: i === 0 ? 'none' : `1px solid ${borderColor}` }}
        >
          <ItemRow item={item} />
        </div>
      ))}
    </div>
  );
}

/**
 * Расчёт показателя — панелью под ведомостью, а не модальным окном.
 *
 * Ведомость остаётся на экране, соседние ячейки кликаются подряд без
 * закрытия панели (вариант A макета, спека доработок 2026-08-03, раздел 6).
 * Кроме списков задач панель показывает воронку отбора — она отвечает не
 * «какие задачи», а «почему их столько».
 */
export default function KpiBreakdownDock({
  target, year, month, direction, teams, onClose,
}: KpiBreakdownDockProps) {
  const t = useThemeTokens();

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

  if (!target) return null;

  const metric = target.row.metrics.find((m) => m.code === target.metricCode);

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
        <span
          className="num"
          style={{ fontSize: 15, fontWeight: 700 }}
        >
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
      ) : (
        <div
          style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(330px, 1fr))',
            gap: 18, padding: 16,
          }}
        >
          <div>
            <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
              Как получилось это число
            </Text>
            <div style={{ marginTop: 7 }}>
              <KpiFunnel steps={query.data?.numerator_funnel ?? []} />
            </div>
            {(query.data?.denominator_funnel.length ?? 0) > 0 && (
              <div style={{ marginTop: 12 }}>
                <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
                  С чем сравниваем — отбор знаменателя
                </Text>
                <div style={{ marginTop: 7 }}>
                  <KpiFunnel steps={query.data?.denominator_funnel ?? []} />
                </div>
              </div>
            )}
          </div>

          <div>
            <Text strong style={{ fontSize: 12.5 }}>Что считаем</Text>
            {(query.data?.numerator.length ?? 0) === 0 ? (
              <Empty description="Нет задач в числителе" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '8px 0' }} />
            ) : (
              <ItemList items={query.data?.numerator ?? []} borderColor={t.border} />
            )}

            {(query.data?.denominator.length ?? 0) > 0 && (
              <div style={{ marginTop: 12 }}>
                <Text strong style={{ fontSize: 12.5 }}>С чем сравниваем</Text>
                <ItemList items={query.data?.denominator ?? []} borderColor={t.border} />
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
