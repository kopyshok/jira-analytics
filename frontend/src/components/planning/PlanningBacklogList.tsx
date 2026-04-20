import { Card, Checkbox, Tag, Tooltip } from 'antd';
import { ROLE_COLORS, DARK_THEME, FONTS } from '../../utils/constants';
import type { BacklogItemResponse, BacklogImpactRisk } from '../../types/api';

interface RoleTotals {
  analyst: number;
  dev: number;
  qa: number;
}

interface Props {
  items: BacklogItemResponse[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  demandByRole: RoleTotals;
  capacityByRole: RoleTotals;
  year: string;
  quarter: string;
}

const IMPACT_COLORS: Record<BacklogImpactRisk, string> = {
  low: 'default',
  medium: 'blue',
  high: 'cyan',
};

const IMPACT_LABELS: Record<BacklogImpactRisk, string> = {
  low: 'низкий',
  medium: 'средний',
  high: 'высокий',
};

const RISK_COLORS: Record<BacklogImpactRisk, string> = {
  low: 'green',
  medium: 'default',
  high: 'warning',
};

const RISK_LABELS: Record<BacklogImpactRisk, string> = {
  low: 'низкий',
  medium: 'средний',
  high: 'высокий',
};

const GRID_COLUMNS = '40px 60px 1fr 200px 75px 100px 95px';

/** Левая колонка /planning: заголовок-Card + одна строка на элемент бэклога
 *  с чекбоксом, приоритетом, названием, разбивкой по ролям АН/ПР/ТС/ОПЭ,
 *  тотом, impact/risk. Mirrors Prototype.html lines 1343-1417. */
export default function PlanningBacklogList({
  items,
  selected,
  onToggle,
  demandByRole,
  capacityByRole,
  year,
  quarter,
}: Props) {
  return (
    <Card
      title={`Бэклог идей на Q${quarter} ${year}`}
      styles={{ body: { padding: 0 } }}
      extra={
        <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
          отсортировано по приоритету · оценка по ролям: АН / ПР / ТС / ОПЭ
        </span>
      }
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: GRID_COLUMNS,
          padding: '8px 14px',
          borderBottom: `1px solid ${DARK_THEME.border}`,
          background: DARK_THEME.darkAccent,
          fontSize: 10,
          color: DARK_THEME.textMuted,
          textTransform: 'uppercase',
          letterSpacing: 0.6,
        }}
      >
        <span>✓</span>
        <span>Прио</span>
        <span>Идея</span>
        <span>АН / ПР / ТС / ОПЭ</span>
        <span style={{ textAlign: 'right' }}>Всего</span>
        <span>Влияние</span>
        <span>Риск</span>
      </div>
      <div style={{ maxHeight: 560, overflowY: 'auto' }}>
        {items.map((item) => {
          const isSel = selected.has(item.id);
          const a = item.estimate_analyst_hours ?? 0;
          const d = item.estimate_dev_hours ?? 0;
          const q = item.estimate_qa_hours ?? 0;
          const o = item.estimate_opo_hours ?? 0;
          const total = item.estimate_hours ?? a + d + q + o;

          // «Не влезает по ролям» — добавление этой задачи толкает любую роль за capacity
          const wouldOver =
            !isSel &&
            ((demandByRole.analyst + a > capacityByRole.analyst && capacityByRole.analyst > 0) ||
              (demandByRole.dev + d > capacityByRole.dev && capacityByRole.dev > 0) ||
              (demandByRole.qa + q > capacityByRole.qa && capacityByRole.qa > 0));
          // Текущая — уже выбранная и какая-то роль в перегрузе по ней
          const currentlyOver =
            isSel &&
            ((a > 0 && demandByRole.analyst > capacityByRole.analyst && capacityByRole.analyst > 0) ||
              (d > 0 && demandByRole.dev > capacityByRole.dev && capacityByRole.dev > 0) ||
              (q > 0 && demandByRole.qa > capacityByRole.qa && capacityByRole.qa > 0));

          const priorityCyan = item.priority != null && item.priority <= 3;
          const rowBg = currentlyOver
            ? 'rgba(245,165,36,0.08)'
            : isSel
              ? 'rgba(0,201,200,0.04)'
              : 'transparent';

          return (
            <div
              key={item.id}
              data-testid={`planning-item-${item.id}`}
              onClick={() => onToggle(item.id)}
              style={{
                display: 'grid',
                gridTemplateColumns: GRID_COLUMNS,
                padding: '12px 14px',
                borderBottom: `1px solid ${DARK_THEME.border}`,
                alignItems: 'center',
                cursor: 'pointer',
                background: rowBg,
                opacity: isSel ? 1 : 0.75,
                transition: 'background .15s',
              }}
            >
              <div onClick={(e) => e.stopPropagation()}>
                <Checkbox checked={isSel} onChange={() => onToggle(item.id)} />
              </div>
              <span
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: 4,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: priorityCyan ? DARK_THEME.cyanPrimary : DARK_THEME.darkAccent,
                  color: priorityCyan ? '#003a3a' : DARK_THEME.textMuted,
                  fontSize: 11,
                  fontWeight: 700,
                  fontFamily: FONTS.mono,
                }}
              >
                {item.priority ?? '—'}
              </span>
              <div>
                <div style={{ color: DARK_THEME.textPrimary, fontSize: 13, marginBottom: 3 }}>
                  {item.title}
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  {item.jira_key && (
                    <span style={{ fontFamily: FONTS.mono, fontSize: 10, color: DARK_THEME.cyanSecondary }}>
                      {item.jira_key}
                    </span>
                  )}
                  {wouldOver && (
                    <Tooltip title="Добавление задачи даст перегруз по одной из ролей">
                      <span style={{ fontSize: 10, color: DARK_THEME.amber }}>не влезает по ролям</span>
                    </Tooltip>
                  )}
                </div>
              </div>
              {/* Breakdown bar — 4 сегмента (АН/ПР/ТС/ОПЭ) пропорциональны часам */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div
                  style={{
                    display: 'flex',
                    height: 16,
                    width: 120,
                    borderRadius: 3,
                    overflow: 'hidden',
                    background: DARK_THEME.darkAccent,
                  }}
                >
                  {total > 0 && a > 0 && (
                    <div
                      title={`Аналитик: ${a} ч`}
                      style={{ width: `${(a / total) * 100}%`, background: ROLE_COLORS.analyst }}
                    />
                  )}
                  {total > 0 && d > 0 && (
                    <div
                      title={`Программист: ${d} ч`}
                      style={{ width: `${(d / total) * 100}%`, background: ROLE_COLORS.dev }}
                    />
                  )}
                  {total > 0 && q > 0 && (
                    <div
                      title={`Тестировщик: ${q} ч`}
                      style={{ width: `${(q / total) * 100}%`, background: ROLE_COLORS.qa }}
                    />
                  )}
                  {total > 0 && o > 0 && (
                    <div
                      title={`ОПЭ: ${o} ч`}
                      style={{ width: `${(o / total) * 100}%`, background: ROLE_COLORS.opo }}
                    />
                  )}
                </div>
                <div
                  style={{
                    fontFamily: FONTS.mono,
                    fontSize: 10,
                    color: DARK_THEME.textHint,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {a}/{d}/{q}/{o}
                </div>
              </div>
              <span
                style={{
                  textAlign: 'right',
                  fontFamily: FONTS.mono,
                  fontSize: 13,
                  color: DARK_THEME.textPrimary,
                }}
              >
                {Math.round(total)} ч
              </span>
              <div>
                {item.impact ? (
                  <Tag color={IMPACT_COLORS[item.impact]}>{IMPACT_LABELS[item.impact]}</Tag>
                ) : (
                  <span style={{ color: DARK_THEME.textDim, fontSize: 11 }}>—</span>
                )}
              </div>
              <div>
                {item.risk ? (
                  <Tag color={RISK_COLORS[item.risk]}>{RISK_LABELS[item.risk]}</Tag>
                ) : (
                  <span style={{ color: DARK_THEME.textDim, fontSize: 11 }}>—</span>
                )}
              </div>
            </div>
          );
        })}
        {items.length === 0 && (
          <div style={{ padding: 24, textAlign: 'center', color: DARK_THEME.textMuted, fontSize: 13 }}>
            Нет записей в бэклоге на Q{quarter} {year}. Добавьте идеи на странице «Бэклог идей».
          </div>
        )}
      </div>
    </Card>
  );
}
