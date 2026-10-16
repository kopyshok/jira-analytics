import { Fragment, useMemo, useState } from 'react';
import { App, Dropdown, Segmented, Spin } from 'antd';
import type { ConflictOut } from '../../../../api/resourcePlanning';
import { usePatchConflict, useExplainConflict } from '../../../../hooks/useResourcePlanning';
import { ExplainBreakdown } from '../../../../components/resource-planning/ConflictPanel';
import {
  CONFLICT_STATUS_LABEL,
  CONFLICT_TYPE_LABELS,
  groupConflicts,
  isLiveConflict,
  splitConflicts,
  type ConflictGroupBy,
} from '../../../../utils/rpConflicts';
import { BlockHead } from '../../components/Passport';
import { WarnIcon } from '../../components/icons';

const SEVERITY_RANK: Record<string, number> = { critical: 0, warning: 1, info: 2 };

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'Критический',
  warning: 'Предупреждение',
};

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

function ConflictCard({ c, planId, onSelectAssignment, onStatusChange }: {
  c: ConflictOut;
  planId: string | null;
  onSelectAssignment?: (assignmentId: string) => void;
  onStatusChange: (conflictId: string, status: ConflictOut['status']) => void;
}) {
  const [showDetails, setShowDetails] = useState(false);
  const isOverload = c.type.startsWith('OVERLOAD_');
  const isLive = isLiveConflict(c);
  const explain = useExplainConflict(planId, c.id, showDetails && isOverload);
  const tone = c.severity === 'critical' ? 'is-critical' : 'is-warning';
  const clickable = !!c.assignment_id && !!onSelectAssignment;
  const status = (
    <span className="sw-chip is-plain" title={isLive ? 'Исчезнет сам, когда причину устранят' : 'Сменить статус'}>
      {CONFLICT_STATUS_LABEL[c.status]}
    </span>
  );
  return (
    <div className={`sw-rp-conflict ${tone}`}>
      <WarnIcon className="sw-rp-conflict-icon" />
      <div className="sw-rp-conflict-body">
        <div className="sw-rp-conflict-sev">{SEVERITY_LABEL[c.severity] ?? c.severity}</div>
        <button
          type="button"
          className="sw-rp-conflict-title"
          disabled={!clickable}
          onClick={() => c.assignment_id && onSelectAssignment?.(c.assignment_id)}
        >
          {CONFLICT_TYPE_LABELS[c.type] ?? 'Конфликт'}
        </button>
        <div className="sw-rp-conflict-msg" title={c.message}>{c.message}</div>
        {isOverload && (
          <button type="button" className="sw-link sw-rp-conflict-more" onClick={() => setShowDetails((v) => !v)}>
            {showDetails ? 'Скрыть расчёт' : 'Расчёт'}
          </button>
        )}
        {showDetails && isOverload && (
          <div className="sw-rp-conflict-explain">
            {explain.isLoading && <Spin size="small" />}
            {explain.data && <ExplainBreakdown data={explain.data} onSelectAssignment={onSelectAssignment} />}
            {explain.isError && <span className="sw-rp-error">Ошибка загрузки расчёта</span>}
          </div>
        )}
      </div>
      {isLive ? status : (
        <Dropdown
          trigger={['click']}
          menu={{
            items: (['acknowledged', 'muted', 'resolved', 'open'] as const)
              .filter((s) => s !== c.status)
              .map((s) => ({ key: s, label: CONFLICT_STATUS_LABEL[s], onClick: () => onStatusChange(c.id, s) })),
          }}
        >
          <button type="button" className="sw-rp-conflict-status">{status}</button>
        </Dropdown>
      )}
    </div>
  );
}

/**
 * Конфликты плана в обложке «Швейцарская»: строка счётчиков, группировка
 * и карточки в три колонки. Те же действия, что у панели Aurora: переход
 * к фазе, смена статуса, расчёт перегрузки, погашенные по запросу.
 */
export default function ConflictStrip({ conflicts, planId, onSelectAssignment }: {
  conflicts: ConflictOut[];
  planId: string | null;
  onSelectAssignment?: (assignmentId: string) => void;
}) {
  const { message } = App.useApp();
  const patchMutation = usePatchConflict(planId);
  const [showHidden, setShowHidden] = useState(false);
  const [groupBy, setGroupBy] = useState<ConflictGroupBy>('item');
  const [expanded, setExpanded] = useState(false);

  const { active, hidden, visible } = useMemo(
    () => splitConflicts(conflicts, showHidden),
    [conflicts, showHidden],
  );
  // Сначала критические — и группы с ними, и внутри группы: они важнее и видны без прокрутки.
  const groups = useMemo(() => {
    const rank = (c: ConflictOut) => SEVERITY_RANK[c.severity] ?? 3;
    return groupConflicts(visible, groupBy)
      .map((g) => ({ ...g, items: [...g.items].sort((a, b) => rank(a) - rank(b)) }))
      .sort((a, b) => rank(a.items[0]) - rank(b.items[0]));
  }, [visible, groupBy]);

  if (active.length === 0 && hidden.length === 0) return null;

  const criticals = active.filter((c) => c.severity === 'critical').length;
  // Свёрнуто — одна строка из трёх самых важных, как в макете; «Подробности» — весь список по группам.
  const ROW = 3;
  const top = groups.flatMap((g) => g.items).sort((a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3)).slice(0, ROW);
  const more = visible.length - top.length;
  const warnings = active.filter((c) => c.severity === 'warning').length;

  const handleStatusChange = (conflictId: string, status: ConflictOut['status']) => {
    patchMutation.mutate(
      { conflictId, status },
      {
        onSuccess: () => message.success(`Статус: ${CONFLICT_STATUS_LABEL[status]}`),
        onError: () => message.error('Ошибка изменения статуса'),
      },
    );
  };

  return (
    <section className="sw-block sw-rp-conflicts">
      <BlockHead
        num="2.2"
        title={
          <>
            Конфликты
            {criticals > 0 && <> · <span className="sw-accent">{criticals} {plural(criticals, 'критический', 'критических', 'критических')}</span></>}
            {warnings > 0 && <> · {warnings} {plural(warnings, 'предупреждение', 'предупреждения', 'предупреждений')}</>}
          </>
        }
      >
        <Segmented
          size="small"
          value={groupBy}
          onChange={(v) => {
            setGroupBy(v as ConflictGroupBy);
            setExpanded(true);
          }}
          options={[
            { label: 'По задачам', value: 'item' },
            { label: 'По сотрудникам', value: 'employee' },
            { label: 'По типу', value: 'type' },
          ]}
        />
        {hidden.length > 0 && (
          <button type="button" className="sw-link" onClick={() => setShowHidden((v) => !v)}>
            {showHidden ? 'Скрыть погашенные' : `Погашенные · ${hidden.length}`}
          </button>
        )}
        {(expanded || more > 0) && (
          <button type="button" className="sw-link" onClick={() => setExpanded((v) => !v)}>
            {expanded ? 'Свернуть' : `Подробности · ещё ${more}`}
          </button>
        )}
      </BlockHead>
      <div className={`sw-rp-conflict-grid${expanded ? ' is-expanded' : ''}`}>
        {!expanded && top.map((c) => (
          <ConflictCard
            key={c.id}
            c={c}
            planId={planId}
            onSelectAssignment={onSelectAssignment}
            onStatusChange={handleStatusChange}
          />
        ))}
        {expanded && groups.map((g) => (
          <Fragment key={g.key}>
            {groups.length > 1 && <div className="sw-rp-conflict-group">{g.label} · {g.items.length}</div>}
            {g.items.map((c) => (
              <ConflictCard
                key={c.id}
                c={c}
                planId={planId}
                onSelectAssignment={onSelectAssignment}
                onStatusChange={handleStatusChange}
              />
            ))}
          </Fragment>
        ))}
      </div>
    </section>
  );
}
