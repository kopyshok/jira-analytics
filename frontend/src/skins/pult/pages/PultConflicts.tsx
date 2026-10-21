import { useState } from 'react';
import { Dropdown, Segmented } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import type { ConflictOut } from '../../../api/resourcePlanning';
import { ConflictAlert } from '../../../components/resource-planning/ConflictPanel';
import {
  CONFLICT_STATUS_LABEL, CONFLICT_TYPE_LABELS, isLiveConflict, useConflictBoard, type ConflictGroupBy,
} from '../../../components/resource-planning/useConflictBoard';
import { PModule } from '../ui';
import { plural } from '../../../utils/plural';

const SEV_LABEL: Record<ConflictOut['severity'], string> = {
  critical: 'КРИТИЧ.',
  warning: 'ПРЕДУПР.',
  info: 'ИНФО',
};

/**
 * Конфликты: счётчики, группировка и лента карточек; «Подробности» —
 * полный разбор (тот же, что в Aurora: расчёт перегрузки, смена статуса).
 */
export default function PultConflicts({ conflicts, planId, onSelectAssignment }: {
  conflicts: ConflictOut[];
  planId: string | null;
  onSelectAssignment?: (assignmentId: string) => void;
}) {
  const board = useConflictBoard(conflicts, planId);
  const { groupBy, setGroupBy, showHidden, setShowHidden, active, hidden, groups, criticals, warnings, handleStatusChange } = board;
  const [details, setDetails] = useState(false);
  const cards = groups.flatMap(g => g.items);

  return (
    <PModule
      title="Конфликты"
      className="rp-conflicts"
      ariaLabel="Конфликты"
      extra={
        <>
          {active.length === 0 && hidden.length === 0 ? (
            <span className="rp-conf-none">конфликтов нет</span>
          ) : (
            <span className="rp-conf-counts">
              <b className="p-count is-red">{criticals.length}</b> {plural(criticals.length, 'критический', 'критических', 'критических')} ·{' '}
              <b className="p-count is-amber">{warnings.length}</b> {plural(warnings.length, 'предупреждение', 'предупреждения', 'предупреждений')}
            </span>
          )}
          {(active.length > 0 || hidden.length > 0) && (
            <Segmented
              size="small"
              value={groupBy}
              onChange={(v) => setGroupBy(v as ConflictGroupBy)}
              options={[
                { label: 'По задачам', value: 'item' },
                { label: 'По сотрудникам', value: 'employee' },
                { label: 'По типу', value: 'type' },
              ]}
            />
          )}
          <span className="pm-push" style={{ display: 'inline-flex', gap: 14 }}>
            {hidden.length > 0 && (
              <button type="button" className="pm-link" onClick={() => setShowHidden(!showHidden)}>
                {showHidden ? 'Скрыть погашенные' : `Показать ${hidden.length} ${plural(hidden.length, 'погашенный', 'погашенных', 'погашенных')}`}
              </button>
            )}
            {cards.length > 0 && (
              <button type="button" className="pm-link" aria-expanded={details} onClick={() => setDetails(v => !v)}>
                {details ? 'Свернуть' : 'Подробности'}
              </button>
            )}
          </span>
        </>
      }
    >
      {cards.length > 0 && !details && (
        <div className="rp-conf-strip">
          {cards.map(c => (
            <div
              key={c.id}
              className={`rp-conf-card${c.assignment_id && onSelectAssignment ? ' is-link' : ''}`}
              role={c.assignment_id ? 'button' : undefined}
              tabIndex={c.assignment_id ? 0 : undefined}
              onClick={() => c.assignment_id && onSelectAssignment?.(c.assignment_id)}
              onKeyDown={(e) => {
                if ((e.key === 'Enter' || e.key === ' ') && c.assignment_id) {
                  e.preventDefault();
                  onSelectAssignment?.(c.assignment_id);
                }
              }}
              title={c.message}
            >
              <span className={`p-sev is-${c.severity}`}>{SEV_LABEL[c.severity]}</span>
              <span className="rp-conf-type">{CONFLICT_TYPE_LABELS[c.type] ?? 'Конфликт'}</span>
              <span className="rp-conf-msg">{c.message}</span>
              <span className="pc-cap rp-conf-status">{CONFLICT_STATUS_LABEL[c.status]}</span>
              {!isLiveConflict(c) && (
                <Dropdown
                  trigger={['click']}
                  menu={{
                    items: (['acknowledged', 'muted', 'resolved', 'open'] as const)
                      .filter(s => s !== c.status)
                      .map(s => ({ key: s, label: CONFLICT_STATUS_LABEL[s], onClick: () => handleStatusChange(c.id, s) })),
                  }}
                >
                  <button
                    type="button"
                    className="rp-conf-more"
                    aria-label="Сменить статус"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MoreOutlined />
                  </button>
                </Dropdown>
              )}
            </div>
          ))}
        </div>
      )}
      {details && (
        <div className="rp-conf-details">
          {groups.map(g => (
            <div key={g.key} className="rp-conf-group">
              <div className="pc-cap">{g.label} · {g.items.length}</div>
              {g.items.map(c => (
                <ConflictAlert
                  key={c.id}
                  conflict={c}
                  planId={planId}
                  onSelectAssignment={onSelectAssignment}
                  onStatusChange={handleStatusChange}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </PModule>
  );
}
