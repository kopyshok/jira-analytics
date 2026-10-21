import { Tooltip, Typography } from 'antd';
import type { SubgroupFlowItem } from '../../types/api';

const { Text } = Typography;

/**
 * Переток внутри команды: часы, ушедшие из группы к соседям и пришедшие от них.
 *
 * Это не «помощь извне» — граница «свои — чужие» остаётся на уровне команды,
 * здесь показан внутренний обмен ресурсом между группами.
 */
export default function SubgroupFlowLine({ items, compact = false, emptyText = 'Группы команды часами между собой не обменивались' }: {
  items?: SubgroupFlowItem[];
  /** Вид скина: отдельная карточка, группы — пилюлями «Группа: −12 ч к соседям · +8 ч от них»;
   *  карточка есть всегда, без перетока — со спокойной подписью. */
  compact?: boolean;
  /** Подпись пустой карточки: перетока нет, команда не выбрана или в ней нет групп — решает страница. */
  emptyText?: string;
}) {
  const rows = (items ?? []).filter((i) => i.out_hours > 0 || i.in_hours > 0);
  if (rows.length === 0 && !compact) return null;

  if (compact) {
    return (
      <section className="wr-card anc-flow" aria-label="Переток внутри команды">
        <Tooltip title="Часы, которыми группы обменялись внутри команды. Помощь извне считается отдельно.">
          <div className="anc-flow-title">Переток внутри команды</div>
        </Tooltip>
        <div className="anc-flow-list">
          {rows.length === 0 && (
            <span className="anc-flow-empty">{emptyText}</span>
          )}
          {rows.map((r) => (
            <span key={r.subgroup_id} className="anc-flow-pill">
              <b>{r.subgroup_name}:</b>
              {r.out_hours > 0 && (
                <span><span className="is-out">−{Math.round(r.out_hours)} ч</span> к соседям</span>
              )}
              {r.out_hours > 0 && r.in_hours > 0 && <span aria-hidden>·</span>}
              {r.in_hours > 0 && (
                <span><span className="is-in">+{Math.round(r.in_hours)} ч</span> от них</span>
              )}
            </span>
          ))}
        </div>
      </section>
    );
  }

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
