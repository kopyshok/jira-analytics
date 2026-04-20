import { Card, Skeleton } from 'antd';
import {
  ROLE_COLORS,
  ROLE_LABELS,
  ROLE_SHORT,
  DARK_THEME,
  FONTS,
  type PlanningRole,
} from '../../utils/constants';
import type { CapacityPreviewResponse } from '../../types/planning';
import RoleCapacityBar from './RoleCapacityBar';

const ROLE_KEYS: Array<Exclude<PlanningRole, 'opo'>> = ['analyst', 'dev', 'qa'];

interface Props {
  preview: CapacityPreviewResponse | undefined;
  quarter: string;
}

function KpiRow({
  k,
  v,
  neg,
  strong,
}: {
  k: string;
  v: string;
  neg?: boolean;
  strong?: boolean;
}) {
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

/** Правая sticky-колонка /planning: 4 карточки с ёмкостью по ролям/сотрудникам. */
export default function PlanningCapacityPanel({
  preview,
  quarter,
}: Props) {
  if (!preview) {
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

  const totalCapacity = preview.total_capacity;
  const totalPlanned = preview.total_demand;
  const overallOver = ROLE_KEYS.some(
    (r) => preview.demand_by_role[r] > preview.capacity_by_role[r] && preview.capacity_by_role[r] > 0,
  );
  const freeHours = Math.max(0, Math.round(totalCapacity - totalPlanned));
  const freePct =
    totalCapacity > 0 ? Math.max(0, Math.round((1 - totalPlanned / totalCapacity) * 100)) : 0;

  // Employees в разрезе ролей для «Расчёт ёмкости» -> последний блок
  const perRoleAgg = ROLE_KEYS.map((r) => {
    const emps = preview.per_employee.filter((e) => e.role === r);
    return {
      role: r,
      empCount: emps.length,
      raw: emps.reduce((s, e) => s + e.raw_hours, 0),
      mandatory: emps.reduce((s, e) => s + e.mandatory_hours, 0),
      capacity: preview.capacity_by_role[r],
    };
  });

  const unroled = preview.per_employee.filter((e) => !ROLE_KEYS.includes(e.role as never));

  // Overall bar (Card 1) — горизонтальный, два сегмента: planned + mandatory
  const plannedPct = totalCapacity > 0 ? Math.min(100, (totalPlanned / totalCapacity) * 100) : 0;

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
            Ёмкость команды · Q{quarter}
          </span>
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
            {Math.round(totalPlanned)}
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
              ? `Запас ${freeHours} ч · ${freePct}% свободно`
              : 'Нет данных о ёмкости на период'}
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
        title="Ёмкость по ролям"
        styles={{ body: { padding: 0 } }}
        extra={<span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>план / доступно</span>}
      >
        <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {ROLE_KEYS.map((r) => (
            <RoleCapacityBar
              key={r}
              role={r}
              demand={preview.demand_by_role[r]}
              capacity={preview.capacity_by_role[r]}
              employeeCount={preview.per_employee.filter((e) => e.role === r).length}
            />
          ))}
        </div>
      </Card>

      {/* 3. Расчёт ёмкости */}
      <Card title="Расчёт ёмкости" styles={{ body: { padding: 0 } }}>
        <div
          style={{
            padding: '10px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            fontSize: 12,
          }}
        >
          <KpiRow
            k={`${preview.per_employee.length} сотр. × календарь РФ`}
            v={`${Math.round(preview.gross_hours).toLocaleString('ru')} ч брутто`}
          />
          <KpiRow k="− Отпуска / отсутствия" v={`−${Math.round(preview.absence_hours)} ч`} neg />
          <KpiRow
            k="− Обязат. работы (сопровожд., встречи)"
            v={`−${Math.round(preview.mandatory_hours)} ч`}
            neg
          />
          <div
            style={{ borderTop: `1px solid ${DARK_THEME.border}`, paddingTop: 8, marginTop: 2 }}
          >
            <KpiRow
              k="Доступно для бэклога"
              v={`${Math.round(preview.available_hours)} ч`}
              strong
            />
          </div>
          {/* В разрезе ролей */}
          <div
            style={{
              marginTop: 8,
              paddingTop: 10,
              borderTop: `1px dashed ${DARK_THEME.border}`,
            }}
          >
            <div
              style={{
                fontSize: 10,
                color: DARK_THEME.textMuted,
                textTransform: 'uppercase',
                letterSpacing: 0.6,
                marginBottom: 8,
              }}
            >
              в разрезе ролей
            </div>
            {perRoleAgg.map((agg) => (
              <div
                key={agg.role}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '8px 1fr auto',
                  gap: 8,
                  padding: '5px 0',
                  alignItems: 'center',
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 2,
                    background: ROLE_COLORS[agg.role],
                    display: 'inline-block',
                  }}
                />
                <span style={{ color: DARK_THEME.textSecondary, fontSize: 12 }}>
                  {ROLE_LABELS[agg.role]}{' '}
                  <span style={{ color: DARK_THEME.textHint, fontSize: 10 }}>
                    ({agg.empCount} чел · брутто {Math.round(agg.raw)} ч − обязат.{' '}
                    {Math.round(agg.mandatory)} ч)
                  </span>
                </span>
                <span
                  style={{
                    fontFamily: FONTS.mono,
                    fontSize: 12,
                    color: ROLE_COLORS[agg.role],
                    fontWeight: 600,
                  }}
                >
                  {Math.round(agg.capacity)} ч
                </span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* 4. По сотрудникам */}
      <Card title="По сотрудникам" styles={{ body: { padding: 0 } }}>
        <div style={{ padding: '8px 14px', display: 'flex', flexDirection: 'column', gap: 9 }}>
          {preview.per_employee.map((e) => {
            const knownRole = ROLE_KEYS.includes(e.role as never)
              ? (e.role as Exclude<PlanningRole, 'opo'>)
              : null;
            const roleColor = knownRole ? ROLE_COLORS[knownRole] : DARK_THEME.textDim;
            const roleShort = knownRole ? ROLE_SHORT[knownRole] : '—';
            const mandPct = e.raw_hours > 0 ? (e.mandatory_hours / e.raw_hours) * 100 : 0;
            const availPct = e.raw_hours > 0 ? (e.available_hours / e.raw_hours) * 100 : 0;
            return (
              <div key={e.employee_id}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'baseline',
                    marginBottom: 4,
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
                      {e.name}
                    </span>
                    {e.vacation_days > 0 && (
                      <span style={{ fontSize: 10, color: DARK_THEME.textHint }}>
                        отп. {e.vacation_days} дн
                      </span>
                    )}
                    {!knownRole && (
                      <span style={{ fontSize: 10, color: DARK_THEME.textDim }}>
                        роль не задана — не учитывается
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
                    {Math.round(e.available_hours)} ч
                  </span>
                </div>
                <div
                  style={{
                    display: 'flex',
                    height: 5,
                    background: DARK_THEME.darkAccent,
                    borderRadius: 2.5,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${mandPct}%`,
                      background: 'rgba(127,119,221,0.5)',
                    }}
                  />
                  <div style={{ width: `${availPct}%`, background: roleColor }} />
                </div>
              </div>
            );
          })}
          {preview.per_employee.length === 0 && (
            <div style={{ color: DARK_THEME.textMuted, fontSize: 12, padding: 8 }}>
              Нет активных сотрудников для периода.
            </div>
          )}
          {unroled.length > 0 && (
            <div style={{ marginTop: 4, fontSize: 10, color: DARK_THEME.textDim }}>
              Сотрудники без роли показаны серым и не учтены в capacity_by_role.
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
