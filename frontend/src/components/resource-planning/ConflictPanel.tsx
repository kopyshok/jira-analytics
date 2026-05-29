import { useMemo, useState } from 'react';
import { Alert, App, Button, Collapse, Dropdown, Segmented, Space, Spin, Tag } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import type { ConflictOut } from '../../api/resourcePlanning';
import { usePatchConflict, useExplainConflict } from '../../hooks/useResourcePlanning';

interface Props {
  conflicts: ConflictOut[];
  planId: string | null;
  onSelectAssignment?: (assignmentId: string) => void;
}

type GroupBy = 'item' | 'employee' | 'type';

const TYPE_LABELS: Record<string, string> = {
  OVERLOAD_HIGH: 'Сильная перегрузка',
  OVERLOAD_MED: 'Средняя перегрузка',
  OVERLOAD_LIGHT: 'Лёгкая перегрузка',
  QUARTER_OVERFLOW: 'Не вмещается в квартал',
  SPLIT_REQUIRED: 'Требуется разбивка',
  NO_ANALYST: 'Нет аналитика',
  NO_DEV: 'Нет разработчика',
  LATE_START: 'Поздний старт',
  PREDECESSOR_VIOLATED: 'Нарушен порядок предшественников',
  LEVELING_DELAY: 'Сдвиг при выравнивании',
  LEVELING_REASSIGN: 'Переназначение',
};

const SEVERITY_TYPE: Record<string, 'error' | 'warning' | 'info'> = {
  critical: 'error',
  warning: 'warning',
  info: 'info',
};

const STATUS_COLOR: Record<ConflictOut['status'], string> = {
  open: 'red',
  acknowledged: 'orange',
  muted: 'default',
  resolved: 'green',
};

const STATUS_LABEL: Record<ConflictOut['status'], string> = {
  open: 'Открыт',
  acknowledged: 'Принят',
  muted: 'Замучен',
  resolved: 'Решён',
};

function ConflictAlert({
  conflict: c,
  planId,
  onSelectAssignment,
  onStatusChange,
}: {
  conflict: ConflictOut;
  planId: string | null;
  onSelectAssignment?: (assignmentId: string) => void;
  onStatusChange: (conflictId: string, status: ConflictOut['status']) => void;
}) {
  const [showDetails, setShowDetails] = useState(false);
  const isOverload = c.type.startsWith('OVERLOAD_');
  const explain = useExplainConflict(planId, c.id, showDetails && isOverload);

  return (
    <Alert
      type={SEVERITY_TYPE[c.severity] ?? 'info'}
      showIcon
      title={
        <div style={{ width: '100%' }}>
          <Space size={8} align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
            <span
              style={{ cursor: c.assignment_id && onSelectAssignment ? 'pointer' : 'default' }}
              onClick={() =>
                c.assignment_id && onSelectAssignment?.(c.assignment_id)
              }
            >
              {c.message}
            </span>
            <Space size={4}>
              {isOverload && (
                <Button
                  size="small"
                  type="link"
                  style={{ padding: 0, fontSize: 12 }}
                  onClick={() => setShowDetails(v => !v)}
                >
                  {showDetails ? 'Скрыть' : 'Подробности'}
                </Button>
              )}
              <Tag color={STATUS_COLOR[c.status]}>{STATUS_LABEL[c.status]}</Tag>
              <Dropdown
                menu={{
                  items: (['acknowledged', 'muted', 'resolved', 'open'] as const)
                    .filter(s => s !== c.status)
                    .map(s => ({
                      key: s,
                      label: STATUS_LABEL[s],
                      onClick: () => onStatusChange(c.id, s),
                    })),
                }}
                trigger={['click']}
              >
                <a><MoreOutlined /></a>
              </Dropdown>
            </Space>
          </Space>
          {showDetails && isOverload && (
            <div style={{ marginTop: 8, padding: 8, background: 'rgba(0,0,0,0.18)', borderRadius: 4 }}>
              {explain.isLoading && <Spin size="small" />}
              {explain.data && (
                <ExplainBreakdown data={explain.data} onSelectAssignment={onSelectAssignment} />
              )}
              {explain.isError && (
                <span style={{ color: '#ef4444', fontSize: 12 }}>Ошибка загрузки расчёта</span>
              )}
            </div>
          )}
        </div>
      }
    />
  );
}

function ExplainBreakdown({
  data,
  onSelectAssignment,
}: {
  data: import('../../api/resourcePlanning').ConflictExplainOut;
  onSelectAssignment?: (assignmentId: string) => void;
}) {
  const avail = data.available_hours ?? 0;
  const demand = data.demand_hours ?? 0;
  const pct = data.overload_pct ?? 0;
  return (
    <div style={{ fontSize: 12, color: '#cfe1f5' }}>
      <div style={{ marginBottom: 6 }}>
        <b>{data.employee_name ?? 'Сотрудник'}</b>
        {data.date && <> · день <b>{data.date}</b></>}
      </div>
      <div style={{ marginBottom: 6 }}>
        Доступно: <b>{avail.toFixed(1)} ч</b> · Назначено: <b>{demand.toFixed(1)} ч</b> ·
        <span style={{ color: pct > 110 ? '#ef4444' : '#ffb432', fontWeight: 700, marginLeft: 4 }}>
          {pct.toFixed(0)}%
        </span>
      </div>
      {data.contributors.length === 0 ? (
        <div style={{ color: '#7a9ab8' }}>Нет перекрывающих назначений</div>
      ) : (
        <>
          <div style={{ color: '#8ab0d8', fontSize: 11, marginBottom: 4 }}>
            Перекрывают день ({data.contributors.length}):
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {data.contributors.map(co => (
              <div
                key={co.assignment_id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '70px 80px 1fr 70px',
                  gap: 8,
                  fontSize: 11,
                  padding: '2px 0',
                  cursor: onSelectAssignment ? 'pointer' : 'default',
                  borderBottom: '1px dashed rgba(120,150,180,0.15)',
                }}
                onClick={() => onSelectAssignment?.(co.assignment_id)}
              >
                <span style={{ color: '#7a9ab8' }}>{co.item_key ?? '—'}</span>
                <span style={{ color: '#8ab0d8' }}>{co.phase_label}</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {co.item_title}
                </span>
                <span style={{ textAlign: 'right', color: '#cfe1f5' }}>
                  {co.hours_per_day.toFixed(2)} ч/день
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function ConflictPanel({ conflicts, planId, onSelectAssignment }: Props) {
  const { message } = App.useApp();
  const patchMutation = usePatchConflict(planId);
  const [showHidden, setShowHidden] = useState(false);
  const [groupBy, setGroupBy] = useState<GroupBy>('item');

  const { active, hidden, visible } = useMemo(() => {
    const nonInfo = conflicts.filter(c => c.severity !== 'info');
    const a = nonInfo.filter(c => c.status !== 'muted' && c.status !== 'resolved');
    const h = nonInfo.filter(c => c.status === 'muted' || c.status === 'resolved');
    return { active: a, hidden: h, visible: showHidden ? [...a, ...h] : a };
  }, [conflicts, showHidden]);

  const groups = useMemo(() => {
    const map = new Map<string, { label: string; items: ConflictOut[] }>();
    for (const c of visible) {
      let key = 'misc';
      let label = '—';
      if (groupBy === 'item') {
        key = c.backlog_item_id ?? 'misc';
        label = c.backlog_item_title ?? 'Без инициативы';
      } else if (groupBy === 'employee') {
        key = c.employee_id ?? 'misc';
        label = c.employee_id
          ? c.employee_name ?? c.employee_id
          : 'Без сотрудника';
      } else {
        key = c.type;
        label = TYPE_LABELS[c.type] ?? c.type;
      }
      if (!map.has(key)) map.set(key, { label, items: [] });
      map.get(key)!.items.push(c);
    }
    return [...map.entries()]
      .map(([key, v]) => ({ key, label: v.label, items: v.items }))
      .sort((a, b) => a.label.localeCompare(b.label, 'ru'));
  }, [visible, groupBy]);

  if (active.length === 0 && hidden.length === 0) return null;

  const criticals = active.filter(c => c.severity === 'critical');
  const warnings = active.filter(c => c.severity === 'warning');

  const handleStatusChange = (conflictId: string, status: ConflictOut['status']) => {
    patchMutation.mutate(
      { conflictId, status },
      {
        onSuccess: () => message.success(`Статус: ${STATUS_LABEL[status]}`),
        onError: () => message.error('Ошибка изменения статуса'),
      }
    );
  };

  return (
    <Collapse
      size="small"
      style={{ marginBottom: 16 }}
      items={[{
        key: '1',
        label: (
          <span>
            Конфликты{' '}
            {criticals.length > 0 && (
              <span style={{ color: '#e85d4a', fontWeight: 700 }}>
                {criticals.length} критических
              </span>
            )}
            {warnings.length > 0 && (
              <span style={{ color: '#ffb432', marginLeft: 8 }}>
                {warnings.length} предупреждений
              </span>
            )}
          </span>
        ),
        children: (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Space style={{ justifyContent: 'space-between' }}>
              <Segmented
                size="small"
                value={groupBy}
                onChange={(v) => setGroupBy(v as GroupBy)}
                options={[
                  { label: 'По задачам', value: 'item' },
                  { label: 'По сотрудникам', value: 'employee' },
                  { label: 'По типу', value: 'type' },
                ]}
              />
              {hidden.length > 0 && (
                <Button
                  size="small"
                  type="link"
                  style={{ padding: 0, fontSize: 12 }}
                  onClick={() => setShowHidden(!showHidden)}
                >
                  {showHidden ? 'Скрыть погашенные' : `Показать ${hidden.length} погашенных`}
                </Button>
              )}
            </Space>
            {groups.map(g => (
              <div key={g.key} style={{ borderTop: '1px solid #1e3a5f', paddingTop: 6 }}>
                <div style={{ fontSize: 12, color: '#8ab0d8', fontWeight: 600, marginBottom: 4 }}>
                  {g.label}{' '}
                  <Tag>{g.items.length}</Tag>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
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
              </div>
            ))}
          </div>
        ),
      }]}
    />
  );
}
