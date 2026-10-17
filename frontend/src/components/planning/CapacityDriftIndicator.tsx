import { useState } from 'react';
import { App, Button } from 'antd';
import { useAcknowledgeDrift, useCapacityDiff, useRevertScenario } from '../../hooks/usePlanning';

const MONTH_NAMES = ['', 'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                     'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

export default function CapacityDriftIndicator({ scenarioId }: { scenarioId: string }) {
  const { notification } = App.useApp();
  const [expanded, setExpanded] = useState(false);
  const { data: diff } = useCapacityDiff(scenarioId, true);
  const acknowledge = useAcknowledgeDrift();
  const revert = useRevertScenario();

  if (!diff?.has_changes) return null;

  const handleRevise = () => {
    revert.mutate(scenarioId, {
      onSuccess: () => notification.info({
        title: 'Сценарий в черновике',
        description: 'Пересмотрите состав инициатив с учётом новой доступности и утвердите снова — будет создана новая ревизия.',
      }),
      onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  return (
    <div style={{
      border: '1px solid var(--drift-border, rgba(245,158,11,0.5))',
      borderRadius: 8,
      background: 'var(--drift-bg, rgba(245,158,11,0.04))',
      padding: '8px 12px',
      marginTop: 8,
    }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
        onClick={() => setExpanded(v => !v)}
      >
        <span style={{ color: 'var(--drift-warn, #f59e0b)' }}>⚠</span>
        <span style={{ fontSize: 12, color: 'var(--drift-warn, #f59e0b)', fontWeight: 600 }}>
          Доступность изменилась ({diff.changed_employees.length} чел.)
        </span>
        <span style={{ color: 'var(--text-muted, #64748b)', fontSize: 11, marginLeft: 'auto' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: 8 }}>
          {diff.changed_employees.map(emp => (
            <div key={emp.employee_id}>
              {emp.left_team_at && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '4px 6px', background: 'var(--drift-bad-bg, rgba(248,113,113,0.10))',
                  borderRadius: 5, fontSize: 12, marginBottom: 3,
                }}>
                  <span style={{ color: 'var(--drift-text, #e2e8f0)', fontWeight: 500, minWidth: 120 }}>
                    {emp.employee_name}
                  </span>
                  <span style={{ color: 'var(--drift-bad, #f87171)', fontWeight: 600 }}>
                    выбыл из команды {emp.left_team_at.split('-').reverse().join('.')}
                  </span>
                </div>
              )}
              {(emp.subgroup_before || emp.subgroup_after) && (
                <div style={{
                  display: 'flex', gap: 8, padding: '4px 6px',
                  background: 'var(--drift-row-bg, rgba(245,158,11,0.07))', borderRadius: 5,
                  fontSize: 12, marginBottom: 3,
                }}>
                  <span style={{ color: 'var(--drift-text, #e2e8f0)', fontWeight: 500, minWidth: 120 }}>
                    {emp.employee_name}
                  </span>
                  <span style={{ color: 'var(--text-muted, #94a3b8)' }}>
                    группа: {emp.subgroup_before ?? 'без группы'} → {emp.subgroup_after ?? 'без группы'}
                  </span>
                </div>
              )}
              {emp.months.map(m => (
                <div key={`${m.year}-${m.month}`} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8, flexWrap: 'wrap',
                  padding: '4px 6px', background: 'var(--drift-row-bg, rgba(245,158,11,0.07))',
                  borderRadius: 5, fontSize: 12, marginBottom: 3,
                }}>
                  <span style={{ color: 'var(--drift-text, #e2e8f0)', fontWeight: 500, minWidth: 120 }}>
                    {emp.employee_name}
                  </span>
                  <span style={{ color: 'var(--text-muted, #94a3b8)' }}>
                    {MONTH_NAMES[m.month]}: {Math.round(m.snapshot_available_hours)} → {Math.round(m.current_available_hours)} ч
                  </span>
                  <span style={{ fontWeight: 700, color: m.delta_hours > 0 ? 'var(--drift-good, #22c55e)' : 'var(--drift-bad, #f87171)' }}>
                    {m.delta_hours > 0 ? '+' : ''}{Math.round(m.delta_hours)} ч
                  </span>
                  {m.absence_changes.map((ac, i) => (
                    <span key={i} style={{ color: 'var(--text-muted, #64748b)', fontSize: 11 }}>
                      {ac.type === 'removed' ? 'Удалено' : 'Добавлено'}:{' '}
                      {ac.reason ?? 'отсутствие'} {ac.start_date}–{ac.end_date}{' '}
                      ({Math.round(ac.hours)} ч)
                    </span>
                  ))}
                </div>
              ))}
            </div>
          ))}
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <Button
              size="small"
              style={{ borderColor: 'var(--drift-warn, #f59e0b)', color: 'var(--drift-warn, #f59e0b)' }}
              loading={revert.isPending}
              onClick={handleRevise}
            >
              Пересмотреть сценарий
            </Button>
            <Button
              size="small"
              style={{ color: 'var(--text-muted, #64748b)' }}
              loading={acknowledge.isPending}
              onClick={() => acknowledge.mutate(scenarioId)}
            >
              Игнорировать
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

