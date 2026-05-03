import { Alert, Collapse } from 'antd';
import type { ConflictOut } from '../../api/resourcePlanning';

interface Props {
  conflicts: ConflictOut[];
}

const SEVERITY_TYPE: Record<string, 'error' | 'warning' | 'info'> = {
  critical: 'error',
  warning: 'warning',
  info: 'info',
};

export default function ConflictPanel({ conflicts }: Props) {
  if (conflicts.length === 0) return null;

  const criticals = conflicts.filter(c => c.severity === 'critical');
  const warnings = conflicts.filter(c => c.severity === 'warning');

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
            {conflicts.map((c, i) => (
              <Alert
                key={i}
                type={SEVERITY_TYPE[c.severity] ?? 'info'}
                message={c.backlog_item_title ? `${c.backlog_item_title}: ${c.message}` : c.message}
                showIcon
              />
            ))}
          </div>
        ),
      }]}
    />
  );
}
