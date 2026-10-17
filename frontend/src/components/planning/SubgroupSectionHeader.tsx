import { useMemo } from 'react';
import { DownOutlined, RightOutlined } from '@ant-design/icons';
import { getRoleColor } from '../../utils/roles';
import { OPO_COLOR } from '../../utils/opo';
import { roleHoursTotals } from '../../utils/scenarioView';
import { pluralRu } from '../../utils/projectsView';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { AllocationResponse, Role } from '../../types/api';

type Props = {
  name: string;
  items: AllocationResponse[];
  collapsed: boolean;
  roles: Role[];
  /** Квартал сценария не раньше отсечки ОПЭ — колонки ОПЭ нет. */
  opoOff?: boolean;
  onToggle: () => void;
  /** Таблица скина: строка секции в классах plc-*, числа без цвета ролей. */
  flat?: boolean;
};

/** Заголовок секции группы в списке идей: название, счёт идей и часы по ролям. */
export default function SubgroupSectionHeader({
  name, items, collapsed, roles, opoOff = false, onToggle, flat = false,
}: Props) {
  const totals = useMemo(() => roleHoursTotals(items, opoOff), [items, opoOff]);

  const cells: Array<[string, number, string]> = [
    ['АН', totals.analyst, getRoleColor(roles, 'analyst')],
    ['ПР', totals.dev, getRoleColor(roles, 'dev')],
    ['ТС', totals.qa, getRoleColor(roles, 'qa')],
  ];
  if (!opoOff) cells.push(['ОПЭ', totals.opo, OPO_COLOR]);

  if (flat) {
    return (
      <div
        data-tour="planning-subgroup-section"
        className="plc-section"
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
      >
        {collapsed ? <RightOutlined aria-hidden /> : <DownOutlined aria-hidden />}
        <span className="plc-section-name">{name}</span>
        <span className="plc-section-count">
          {items.length} {pluralRu(items.length, ['идея', 'идеи', 'идей'])} · включено {totals.included}
        </span>
        <span className="plc-section-sums">
          {cells.map(([label, hours]) => (
            <span key={label}>{label} <b>{Math.round(hours).toLocaleString('ru')}</b></span>
          ))}
          <b className="plc-section-total">{Math.round(totals.total).toLocaleString('ru')} ч</b>
        </span>
      </div>
    );
  }

  return (
    <div
      data-tour="planning-subgroup-section"
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
