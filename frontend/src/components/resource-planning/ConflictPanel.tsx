import { Alert, App, Collapse, Dropdown, Space, Tag } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import type { ConflictOut } from '../../api/resourcePlanning';
import { usePatchConflict } from '../../hooks/useResourcePlanning';

interface Props {
  conflicts: ConflictOut[];
  planId: string | null;
}

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

export default function ConflictPanel({ conflicts, planId }: Props) {
  const { message } = App.useApp();
  const patchMutation = usePatchConflict(planId);

  // По умолчанию скрываем muted + resolved
  const visible = conflicts.filter(c => c.status !== 'muted' && c.status !== 'resolved');
  if (visible.length === 0) return null;

  const criticals = visible.filter(c => c.severity === 'critical');
  const warnings = visible.filter(c => c.severity === 'warning');

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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {(() => {
              const hiddenCount = conflicts.length - visible.length;
              return hiddenCount > 0 ? (
                <div style={{ fontSize: 12, color: '#7090b0', marginBottom: 8, fontStyle: 'italic' }}>
                  Скрыто: {hiddenCount} (mute/resolved)
                </div>
              ) : null;
            })()}
            {visible.map(c => (
              <Alert
                key={c.id}
                type={SEVERITY_TYPE[c.severity] ?? 'info'}
                showIcon
                message={
                  <Space size={8} align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
                    <span>
                      {c.backlog_item_title ? `${c.backlog_item_title}: ${c.message}` : c.message}
                    </span>
                    <Space size={4}>
                      <Tag color={STATUS_COLOR[c.status]}>{STATUS_LABEL[c.status]}</Tag>
                      <Dropdown
                        menu={{
                          items: (['acknowledged', 'muted', 'resolved', 'open'] as const)
                            .filter(s => s !== c.status)
                            .map(s => ({
                              key: s,
                              label: STATUS_LABEL[s],
                              onClick: () => handleStatusChange(c.id, s),
                            })),
                        }}
                        trigger={['click']}
                      >
                        <a><MoreOutlined /></a>
                      </Dropdown>
                    </Space>
                  </Space>
                }
              />
            ))}
          </div>
        ),
      }]}
    />
  );
}
