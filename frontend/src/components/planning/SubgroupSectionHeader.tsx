import { useMemo } from 'react';
import { DownOutlined, RightOutlined } from '@ant-design/icons';
import { effectiveEstimate } from '../../utils/allocationEstimates';
import { getRoleColor } from '../../utils/roles';
import { OPO_COLOR } from '../../utils/opo';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { AllocationResponse, Role } from '../../types/api';

type Props = {
  name: string;
  items: AllocationResponse[];
  collapsed: boolean;
  roles: Role[];
  onToggle: () => void;
};

/** Заголовок секции группы в списке идей: название, счёт идей и часы по ролям. */
export default function SubgroupSectionHeader({ name, items, collapsed, roles, onToggle }: Props) {
  const totals = useMemo(() => {
    let analyst = 0;
    let dev = 0;
    let qa = 0;
    let opo = 0;
    let included = 0;
    for (const a of items) {
      const eff = effectiveEstimate(a);
      analyst += eff.analyst;
      dev += eff.dev;
      qa += eff.qa;
      opo += eff.opo;
      if (a.included) included += 1;
    }
    return { analyst, dev, qa, opo, included, total: analyst + dev + qa + opo };
  }, [items]);

  const cells: Array<[string, number, string]> = [
    ['АН', totals.analyst, getRoleColor(roles, 'analyst')],
    ['ПР', totals.dev, getRoleColor(roles, 'dev')],
    ['ТС', totals.qa, getRoleColor(roles, 'qa')],
    ['ОПЭ', totals.opo, OPO_COLOR],
  ];

  return (
    <div
      onClick={onToggle}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '7px 14px',
        cursor: 'pointer',
        background: DARK_THEME.darkAccent,
        borderTop: `1px solid ${DARK_THEME.border}`,
        borderBottom: `1px solid ${DARK_THEME.border}`,
        userSelect: 'none',
      }}
    >
      {collapsed ? (
        <RightOutlined style={{ fontSize: 11, color: DARK_THEME.textMuted }} />
      ) : (
        <DownOutlined style={{ fontSize: 11, color: DARK_THEME.textMuted }} />
      )}
      <span style={{ fontSize: 13, fontWeight: 600, color: DARK_THEME.textPrimary }}>{name}</span>
      <span style={{ fontSize: 11, color: DARK_THEME.textHint }}>
        {items.length} идей · включено {totals.included}
      </span>
      <span style={{ flex: 1 }} />
      {cells.map(([label, hours, color]) => (
        <span key={label} style={{ fontSize: 11, color: DARK_THEME.textHint }}>
          {label}{' '}
          <span style={{ fontFamily: FONTS.mono, fontSize: 12, color }}>{Math.round(hours)}</span>
        </span>
      ))}
      <span style={{ fontFamily: FONTS.mono, fontSize: 13, color: DARK_THEME.textPrimary, minWidth: 64, textAlign: 'right' }}>
        {Math.round(totals.total).toLocaleString('ru')} ч
      </span>
    </div>
  );
}
