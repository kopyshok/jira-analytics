import { useMemo } from 'react';
import { Card, Skeleton, Tag } from 'antd';
import { DARK_THEME, FONTS } from '../../utils/constants';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel, getRoleColor } from '../../utils/roles';
import type { AllocationResponse, ResourceBase } from '../../types/api';
import { demandByRole } from '../../utils/planning';
import RoleCapacityBar from './RoleCapacityBar';

const ROLE_KEYS = ['analyst', 'dev', 'qa'] as const;
type RoleKey = (typeof ROLE_KEYS)[number];

// Short abbreviations for role badges in the employee list
const ROLE_SHORT_LOCAL: Record<string, string> = {
  analyst: 'АН',
  dev: 'ПР',
  qa: 'ТС',
  consultant: 'КН',
  other: 'ДР',
};

interface Props {
  resourceBase: ResourceBase | undefined;
  allocations: AllocationResponse[];
  quarter: string;
}

function KpiRow({ k, v, neg, strong }: { k: string; v: string; neg?: boolean; strong?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
      <span
        style={{
          color: strong ? DARK_THEME.textPrimary : DARK_THEME.textMuted,
          fontSize: 12,
          fontWeight: strong ? 600 : 400,
        }}
      >
        {k}
      </span>
      <span
        style={{
          color: neg ? DARK_THEME.amber : strong ? DARK_THEME.cyanPrimary : DARK_THEME.textSecondary,
          fontFamily: FONTS.mono,
          fontSize: 12,
          fontWeight: strong ? 600 : 400,
        }}
      >
        {v}
      </span>
    </div>
  );
}

/** Правая sticky-колонка /planning: карточки с ресурсом по ролям и сотрудникам.
 *  Ёмкость берётся из resourceBase (Task 24, /scenarios/:id/resource).
 *  Потребность считается на клиенте через demandByRole — мгновенно при клике. */
export default function PlanningCapacityPanel({ resourceBase, allocations, quarter }: Props) {
  const { data: roles = [] } = useRoles();

  // Пересчёт потребности по ролям при каждом изменении раскладок — O(n), <1ms
  const demand = useMemo(() => demandByRole(allocations), [allocations]);

  if (!resourceBase) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, position: 'sticky', top: 16 }}>
        <Card>
          <Skeleton active paragraph={{ rows: 3 }} />
        </Card>
        <Card>
          <Skeleton active paragraph={{ rows: 4 }} />
        </Card>
        <Card>
          <Skeleton active paragraph={{ rows: 5 }} />
        </Card>
      </div>
    );
  }

  const capacityByRole: Record<RoleKey, number> = {
    analyst: resourceBase.role_totals['analyst'] ?? 0,
    dev:     resourceBase.role_totals['dev'] ?? 0,
    // Если задан внешний QA-резерв — используем его, иначе берём из role_totals
    qa: resourceBase.external_qa_hours != null
      ? resourceBase.external_qa_hours
      : (resourceBase.role_totals['qa'] ?? 0),
  };

  const totalCapacity = ROLE_KEYS.reduce((s, r) => s + capacityByRole[r], 0);
  const totalDemand = ROLE_KEYS.reduce((s, r) => s + (demand[r] ?? 0), 0);
  const overallOver = ROLE_KEYS.some(
    (r) => (demand[r] ?? 0) > capacityByRole[r] && capacityByRole[r] > 0,
  );
  const freeHours = Math.max(0, Math.round(totalCapacity - totalDemand));
  const freePct = totalCapacity > 0
    ? Math.max(0, Math.round((1 - totalDemand / totalCapacity) * 100))
    : 0;
  const plannedPct = totalCapacity > 0
    ? Math.min(100, (totalDemand / totalCapacity) * 100)
    : 0;

  const includedCount = allocations.filter((a) => a.included).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, position: 'sticky', top: 16 }}>
      {/* 1. Overall gauge */}
      <Card>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            marginBottom: 10,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: DARK_THEME.textMuted,
              textTransform: 'uppercase',
              letterSpacing: 0.8,
            }}
          >
            Ресурс команды · Q{quarter}
          </span>
          {resourceBase.external_qa_hours != null && (
            <Tag color="purple" style={{ fontSize: 10, lineHeight: '18px' }}>
              внешний QA {Math.round(resourceBase.external_qa_hours)} ч
            </Tag>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
          <span
            style={{
              fontSize: 42,
              fontWeight: 700,
              color: overallOver ? DARK_THEME.amber : DARK_THEME.textPrimary,
              fontFamily: FONTS.mono,
              lineHeight: 1,
            }}
          >
            {Math.round(totalDemand)}
          </span>
          <span style={{ fontSize: 16, color: DARK_THEME.textMuted }}>/</span>
          <span style={{ fontSize: 24, color: DARK_THEME.textMuted, fontFamily: FONTS.mono }}>
            {Math.round(totalCapacity)} ч
          </span>
        </div>
        <div style={{ fontSize: 11, color: DARK_THEME.textHint, marginBottom: 10 }}>
          {overallOver
            ? 'Перегруз по одной или нескольким ролям — см. ниже'
            : totalCapacity > 0
              ? `Запас ${freeHours} ч · ${freePct}% свободно · включено ${includedCount} идей`
              : 'Нет данных о ёмкости'}
        </div>
        <div
          style={{
            position: 'relative',
            height: 14,
            background: DARK_THEME.darkAccent,
            borderRadius: 7,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              bottom: 0,
              width: `${plannedPct}%`,
              background: overallOver ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
              transition: 'width .2s',
            }}
          />
        </div>
      </Card>

      {/* 2. Per-role */}
      <Card
        title="Ресурс по ролям"
        styles={{ body: { padding: 0 } }}
        extra={<span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>план / доступно</span>}
      >
        <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {ROLE_KEYS.map((r) => (
            <RoleCapacityBar
              key={r}
              role={r}
              demand={demand[r] ?? 0}
              capacity={capacityByRole[r]}
              employeeCount={resourceBase.employees.filter((e) => e.role === r).length}
            />
          ))}
        </div>
      </Card>

      {/* 3. По сотрудникам */}
      <Card title="По сотрудникам" styles={{ body: { padding: 0 } }}>
        <div style={{ padding: '8px 14px', display: 'flex', flexDirection: 'column', gap: 9 }}>
          {resourceBase.employees.map((e) => {
            const knownRole = e.role && (ROLE_KEYS as readonly string[]).includes(e.role) ? e.role : null;
            const roleColor = knownRole ? getRoleColor(roles, knownRole) : DARK_THEME.textDim;
            const roleShort = knownRole
              ? (ROLE_SHORT_LOCAL[knownRole] ?? knownRole.slice(0, 2).toUpperCase())
              : '—';
            return (
              <div key={e.employee_id}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        width: 22,
                        height: 16,
                        borderRadius: 3,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: roleColor,
                        color: '#00202a',
                        fontSize: 9,
                        fontWeight: 700,
                        fontFamily: FONTS.mono,
                      }}
                    >
                      {roleShort}
                    </span>
                    <span
                      style={{
                        color: knownRole ? DARK_THEME.textPrimary : DARK_THEME.textMuted,
                        fontSize: 12,
                      }}
                    >
                      {e.display_name}
                    </span>
                    {!knownRole && (
                      <span style={{ fontSize: 10, color: DARK_THEME.textDim }}>
                        роль не задана
                      </span>
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      color: DARK_THEME.textMuted,
                      fontFamily: FONTS.mono,
                    }}
                  >
                    {Math.round(e.total_hours)} ч
                  </span>
                </div>
                {/* Simple capacity bar */}
                <div
                  style={{
                    display: 'flex',
                    height: 4,
                    background: DARK_THEME.darkAccent,
                    borderRadius: 2,
                    overflow: 'hidden',
                    marginTop: 4,
                  }}
                >
                  <div style={{ width: '100%', background: roleColor, opacity: 0.4 }} />
                </div>
              </div>
            );
          })}
          {resourceBase.employees.length === 0 && (
            <div style={{ color: DARK_THEME.textMuted, fontSize: 12, padding: 8 }}>
              Нет сотрудников в команде.
            </div>
          )}
        </div>
      </Card>

      {/* 4. Ёмкость по ролям — сводка */}
      <Card title="Ёмкость по ролям" styles={{ body: { padding: 0 } }}>
        <div
          style={{
            padding: '10px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            fontSize: 12,
          }}
        >
          {ROLE_KEYS.map((r) => {
            const cap = capacityByRole[r];
            const dem = demand[r] ?? 0;
            return (
              <KpiRow
                key={r}
                k={`${getRoleLabel(roles, r)} · ${resourceBase.employees.filter((e) => e.role === r).length} чел`}
                v={`${Math.round(dem)} / ${Math.round(cap)} ч`}
                neg={dem > cap && cap > 0}
                strong={false}
              />
            );
          })}
          <div style={{ borderTop: `1px solid ${DARK_THEME.border}`, paddingTop: 8, marginTop: 2 }}>
            <KpiRow
              k="Итого доступно для бэклога"
              v={`${Math.round(totalCapacity)} ч`}
              strong
            />
          </div>
        </div>
      </Card>
    </div>
  );
}
