import { useQuery } from '@tanstack/react-query';
import { Modal, Typography, Space, Tag, Empty, Spin, List } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import {
  fetchBreakdown, isWorklogItem, type KpiBreakdownItem, type KpiReportRow,
} from '../../api/kpi';

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
          <Tag style={{ margin: 0, flex: '0 0 auto' }}>{item.resolution ?? item.status ?? '—'}</Tag>
        )}
      </div>
    </List.Item>
  );
}

export default function KpiBreakdownModal({ target, year, month, direction, onClose }: KpiBreakdownModalProps) {
  const t = useThemeTokens();

  const query = useQuery({
    queryKey: [
      'kpi', 'breakdown', target?.row.account_id, target?.metricCode, year, month, target?.row.team, direction,
    ],
    queryFn: ({ signal }) => fetchBreakdown(
      {
        account_id: target!.row.account_id, metric_code: target!.metricCode, year, month,
        teams: target?.row.team ?? undefined, direction,
      },
      signal,
    ),
    enabled: !!target,
  });

  const metric = target?.row.metrics.find((m) => m.code === target.metricCode);

  return (
    <Modal
      title={target?.metricName}
      open={!!target}
      onCancel={onClose}
      footer={null}
      width={640}
    >
      {query.isLoading ? (
        <div style={{ display: 'grid', placeItems: 'center', minHeight: 160 }}><Spin /></div>
      ) : (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          <div
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14,
              padding: '12px 4px', borderBottom: `1px solid ${t.border}`,
            }}
          >
            <div className="num" style={{ fontSize: 24, fontWeight: 800 }}>
              {metric?.numerator != null ? Math.round(metric.numerator * 10) / 10 : '—'}
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 500, margin: '0 6px' }}>из</Text>
              {metric?.denominator != null ? Math.round(metric.denominator * 10) / 10 : '—'}
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
