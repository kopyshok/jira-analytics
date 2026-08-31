import { Tooltip, Typography } from 'antd';
import type { SubgroupFlowItem } from '../../types/api';

const { Text } = Typography;

/**
 * Переток внутри команды: часы, ушедшие из группы к соседям и пришедшие от них.
 *
 * Это не «помощь извне» — граница «свои — чужие» остаётся на уровне команды,
 * здесь показан внутренний обмен ресурсом между группами.
 */
export default function SubgroupFlowLine({ items }: { items?: SubgroupFlowItem[] }) {
  const rows = (items ?? []).filter((i) => i.out_hours > 0 || i.in_hours > 0);
  if (rows.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 12 }}>
      <Tooltip title="Часы, которыми группы обменялись внутри команды. Помощь извне считается отдельно.">
        <Text type="secondary" style={{ fontSize: 12 }}>
          Переток внутри команды
        </Text>
      </Tooltip>
      {rows.map((r) => (
        <span key={r.subgroup_id} style={{ fontSize: 12 }}>
          <Text>{r.subgroup_name}</Text>{' '}
          {r.out_hours > 0 && (
            <Text type="warning">−{Math.round(r.out_hours)} ч к соседям</Text>
          )}
          {r.out_hours > 0 && r.in_hours > 0 && <Text type="secondary"> · </Text>}
          {r.in_hours > 0 && (
            <Text type="success">+{Math.round(r.in_hours)} ч от них</Text>
          )}
        </span>
      ))}
    </div>
  );
}
