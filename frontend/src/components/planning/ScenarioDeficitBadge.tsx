import { Tooltip } from 'antd';
import { FONTS } from '../../utils/constants';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel, getRoleColor } from '../../utils/roles';

interface Props {
  deficit: Record<string, number>; // role_code -> hours short
}

export default function ScenarioDeficitBadge({ deficit }: Props) {
  const { data: roles = [] } = useRoles();
  const entries = Object.entries(deficit);
  if (entries.length === 0) return null;
  return (
    <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      {entries.map(([role, hours]) => {
        const color = getRoleColor(roles, role);
        const label = getRoleLabel(roles, role);
        const shortLabel =
          role === 'RP' ? 'РП' :
          role === 'project_manager' ? 'РП' :
          role === 'analyst' ? 'АН' :
          role === 'dev' ? 'ПР' :
          role === 'qa' ? 'ТС' :
          role === 'consultant' ? 'КС' :
          (label || role).slice(0, 2);
        return (
          <Tooltip key={role} title={`${label}: дефицит ${hours} ч`}>
            <span
              className="deficit-pulse"
              style={{
                fontFamily: FONTS.mono,
                fontSize: 11,
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: 10,
                background: 'rgba(245, 34, 45, 0.12)',
                color: '#ff7875',
                border: `1px solid ${color}40`,
                whiteSpace: 'nowrap',
              }}
            >
              −{hours}ч {shortLabel}
            </span>
          </Tooltip>
        );
      })}
    </div>
  );
}
