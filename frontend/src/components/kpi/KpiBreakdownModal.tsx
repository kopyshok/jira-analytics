import { useQuery } from '@tanstack/react-query';
import { Modal, Typography, Space, Tag, Empty, Spin, List, Alert, Button } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
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

export interface KpiBreakdownModalProps {
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

function ItemRow({ item }: { item: KpiBreakdownItem }) {
  const worklog = isWorklogItem(item);
  return (
    <List.Item style={{ padding: '8px 4px' }}>
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
    </List.Item>
  );
}

export default function KpiBreakdownModal({ target, year, month, direction, teams, onClose }: KpiBreakdownModalProps) {
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

  const metric = target?.row.metrics.find((m) => m.code === target.metricCode);

  return (
    <Modal
      title={target && (
        <div>
          <div>{target.metricName}</div>
          {/* Подзаголовок «сотрудник, команда, период» — из макета, раньше
              не был перенесён (см. ревью, «из макета не перенесено»). */}
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
            {target.row.employee_name}
            {target.row.team ? ` · ${target.row.team}` : ' · без команды'}
            {` · ${KPI_MONTH_ABBR_RU[month - 1]} ${year}`}
          </Text>
        </div>
      )}
      open={!!target}
      onCancel={onClose}
      footer={null}
      width={640}
    >
      {query.isLoading ? (
        <div style={{ display: 'grid', placeItems: 'center', minHeight: 160 }}><Spin /></div>
      ) : query.isError ? (
        <Alert
          type="error"
          showIcon
          title="Не удалось загрузить расшифровку"
          description={(query.error as Error).message}
          action={<Button size="small" onClick={() => query.refetch()}>Повторить</Button>}
        />
      ) : (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          <div
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14,
              padding: '12px 4px', borderBottom: `1px solid ${t.border}`,
            }}
          >
            <div className="num" style={{ fontSize: 24, fontWeight: 800 }}>
              {/* Дробь берётся из тех же чисел, что и списки задач ниже
                  (numerator_count/denominator_count), а не из значения метрики
                  в отчёте — иначе для «норматив к факту»/«балл к максимуму»
                  дробь показывала бы норматив/балл, а не число задач под ней
                  (см. BLOCKER 2 ревью). */}
              {query.data?.numerator_count ?? '—'}
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 500, margin: '0 6px' }}>из</Text>
              {query.data?.denominator_count ?? '—'}
            </div>
            <div style={{ textAlign: 'right', fontSize: 11.5 }}>
              <div>
                <Text type="secondary">Значение </Text>
                <b className="num">{metric?.has_data ? `${Math.round(metric.value ?? 0)}%` : 'нет данных'}</b>
              </div>
              {target?.row.target_pct != null && (
                <div>
                  <Text type="secondary">Цель </Text>
                  <b className="num">{target.row.target_pct}%</b>
                </div>
              )}
            </div>
          </div>

          <div>
            <Text strong style={{ fontSize: 12.5 }}>Что считаем</Text>
            {(query.data?.numerator.length ?? 0) === 0 ? (
              <Empty description="Нет задач в числителе" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '8px 0' }} />
            ) : (
              <List
                size="small"
                dataSource={query.data?.numerator ?? []}
                renderItem={(item) => <ItemRow item={item} />}
              />
            )}
          </div>

          {(query.data?.denominator.length ?? 0) > 0 && (
            <div>
              <Text strong style={{ fontSize: 12.5 }}>С чем сравниваем</Text>
              <List
                size="small"
                dataSource={query.data?.denominator ?? []}
                renderItem={(item) => <ItemRow item={item} />}
              />
            </div>
          )}
        </Space>
      )}
    </Modal>
  );
}
