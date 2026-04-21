import { DARK_THEME, FONTS } from '../../utils/constants';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel, getRoleColor } from '../../utils/roles';

interface Props {
  role: string;
  demand: number;
  capacity: number;
  employeeCount: number;
}

/** Одна из трёх строк в карточке «Ресурс по ролям» — прогресс-бар с
 *  маркером 100 %, оранжевой «перегруз»-зоной и подписью запас/перегруз.
 *  Mirrors Prototype.html lines 1444-1491. */
export default function RoleCapacityBar({ role, demand, capacity, employeeCount }: Props) {
  const { data: roles = [] } = useRoles();
  const over = demand > capacity;
  const fillPct = capacity > 0 ? Math.min(100, (demand / capacity) * 100) : 0;
  const overflowPct = over && capacity > 0 ? Math.min(40, ((demand - capacity) / capacity) * 100) : 0;
  const loadPct = capacity > 0 ? Math.round((demand / capacity) * 100) : 0;
  const roleColor = getRoleColor(roles, role);

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: 6,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              background: roleColor,
              display: 'inline-block',
            }}
          />
          <span style={{ color: DARK_THEME.textPrimary, fontSize: 13, fontWeight: 500 }}>
            {getRoleLabel(roles, role)}
          </span>
          <span style={{ color: DARK_THEME.textHint, fontSize: 11 }}>· {employeeCount} чел.</span>
        </div>
        <div style={{ fontFamily: FONTS.mono, fontSize: 12 }}>
          <span
            data-testid={`capacity-${role}-demand`}
            style={{
              color: over ? DARK_THEME.amber : DARK_THEME.textPrimary,
              fontWeight: 600,
            }}
          >
            {Math.round(demand)}
          </span>
          <span style={{ color: DARK_THEME.textMuted }}> / {Math.round(capacity)} ч</span>
        </div>
      </div>
      <div
        style={{
          position: 'relative',
          height: 10,
          background: DARK_THEME.darkAccent,
          borderRadius: 5,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: `${fillPct}%`,
            background: over ? DARK_THEME.amber : roleColor,
            borderRadius: 5,
            transition: 'width .2s',
          }}
        />
        {/* 100% marker — stays at right inner edge */}
        <div
          style={{
            position: 'absolute',
            right: 0,
            top: -2,
            bottom: -2,
            width: 2,
            background: DARK_THEME.textSecondary,
          }}
        />
      </div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginTop: 4,
          fontSize: 10,
          color: DARK_THEME.textHint,
          fontFamily: FONTS.mono,
        }}
      >
        <span>
          {over
            ? `перегруз +${Math.round(demand - capacity)} ч`
            : `запас ${Math.round(capacity - demand)} ч`}
        </span>
        <span>загрузка {loadPct}%</span>
      </div>
    </div>
  );
}
