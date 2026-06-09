import React, { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Card, Skeleton, Tooltip } from 'antd';
import { useScenarioResourceSummary } from '../../hooks/usePlanning';
import { useRoles } from '../../hooks/useRoles';
import { getRoleLabel, getRoleColor } from '../../utils/roles';
import { DARK_THEME, FONTS } from '../../utils/constants';
import { demandByAssigneeRole, demandByRole } from '../../utils/planning';
import type { AllocationResponse, ResourceEmployee } from '../../types/api';

interface Props {
  scenarioId: string;
  enabled: boolean;
  allocations?: AllocationResponse[];
  employees?: ResourceEmployee[];
  pulsedRoles?: Set<string>;
}

const CELL: React.CSSProperties = {
  padding: '7px 10px',
  textAlign: 'right' as const,
  fontFamily: FONTS.mono,
  fontSize: 14,
};

const CELL_LABEL: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 13,
  color: DARK_THEME.textMuted,
};

const ROW_DIVIDER = `1px solid rgba(255,255,255,0.06)`;

function ScenarioResourceSummaryBase({ scenarioId, enabled, allocations, employees, pulsedRoles }: Props) {
  const { data: summary, isLoading } = useScenarioResourceSummary(scenarioId, enabled);
  const { data: roles = [] } = useRoles();

  const LS_KEY = 'planning_resource_table_collapsed';
  // 3-state override:
  //   'auto'            — следуем за scroll (isStuck)
  //   'force-expanded'  — юзер кликнул «Развернуть» пока isStuck=true,
  //                       держим развёрнутым, пока он не вернётся к верху
  //   'force-collapsed' — юзер сам свернул в верху страницы, держим свёрнутым
  //                       (персистится в localStorage)
  type Mode = 'auto' | 'force-expanded' | 'force-collapsed';
  const [mode, setMode] = useState<Mode>(
    () => (localStorage.getItem(LS_KEY) === 'true' ? 'force-collapsed' : 'auto'),
  );
  const [isStuck, setIsStuck] = useState(false);
  // Sentinel — 1px блок СНАРУЖИ и ВЫШЕ sticky. Проверяем его top через
  // getBoundingClientRect при скролле. Sentinel в обычном потоке, его высота
  // не меняется от сжатия sticky → нет обратной связи collapse↔measure
  // (которая раньше давала автоколебание: сжимаемся → документ короче →
  // scrollY клампится → sticky отлипает → разворачиваемся → опять прилипает).
  // Callback-ref state: sentinel рендерится после загрузки данных (компонент
  // имеет ранние return), useEffect с deps:[sentinelEl] перепривязывает
  // listener когда DOM-узел появляется.
  const [sentinelEl, setSentinelEl] = useState<HTMLDivElement | null>(null);
  // Хитрая логика чтобы автоколебание не возвращалось:
  //   1. lockoutUntilRef — пока collapse-анимация идёт, не реагируем на scroll-
  //      события (height interpolates → page shrinks → scrollY clamping
  //      порождает фейковые scroll события, не от пользователя).
  //   2. expandBaselineRef — после lockout фиксируем sentinel.top как baseline
  //      (включает любой clamp-прыжок). Expand триггерится только если
  //      sentinel.top > baseline + 20 — значит юзер реально скроллил вверх
  //      относительно того положения, к которому пришли после collapse.
  const heightsRef = useRef<{ full: number; collapsed: number }>({ full: 0, collapsed: 0 });
  const lockoutUntilRef = useRef<number>(0);
  const expandBaselineRef = useRef<number | null>(null);

  useEffect(() => {
    if (!sentinelEl) return;
    const update = () => {
      const top = sentinelEl.getBoundingClientRect().top;
      const now = performance.now();
      setIsStuck((prev) => {
        if (!prev) {
          if (top <= 0) {
            // Транзишен 0.8s — даём 850мс на settling layout + clamp.
            lockoutUntilRef.current = now + 850;
            expandBaselineRef.current = null;
            return true;
          }
          return false;
        }
        // Stuck. До конца lockout — не меняем состояние.
        if (now < lockoutUntilRef.current) return prev;
        // Первое чтение после lockout — фиксируем baseline.
        if (expandBaselineRef.current === null) {
          expandBaselineRef.current = top;
        }
        return top > expandBaselineRef.current + 20 ? false : prev;
      });
      // Sentinel снова в viewport — снимаем force-expanded, чтобы auto-collapse
      // на следующем скролле вниз снова работал.
      if (top > 0) {
        setMode((m) => (m === 'force-expanded' ? 'auto' : m));
      }
    };
    update();
    // Layout-обёртка может скроллить контент во вложенном контейнере
    // (overflow:auto/scroll/overlay), и тогда window не получает scroll-событий.
    // Слушаем и window, и всех scrollable-предков sentinel.
    const scrollers: (Window | HTMLElement)[] = [window];
    let node: HTMLElement | null = sentinelEl.parentElement;
    while (node) {
      const style = getComputedStyle(node);
      if (/(auto|scroll|overlay)/.test(style.overflowY + style.overflow)) {
        scrollers.push(node);
      }
      node = node.parentElement;
    }
    scrollers.forEach((s) => s.addEventListener('scroll', update, { passive: true }));
    window.addEventListener('resize', update, { passive: true });
    return () => {
      scrollers.forEach((s) => s.removeEventListener('scroll', update));
      window.removeEventListener('resize', update);
    };
  }, [sentinelEl]);

  const collapsed =
    mode === 'force-collapsed' || (mode === 'auto' && isStuck);

  const toggleCollapsed = () => {
    if (collapsed) {
      // Разворачиваем: если сейчас auto+stuck — нужен force-expanded, иначе auto.
      const next: Mode = isStuck && mode !== 'force-collapsed' ? 'force-expanded' : 'auto';
      setMode(next);
      localStorage.setItem(LS_KEY, 'false');
    } else {
      // Сворачиваем: если scroll и так свернул бы — auto хватит, иначе force-collapsed.
      const next: Mode = isStuck ? 'auto' : 'force-collapsed';
      setMode(next);
      localStorage.setItem(LS_KEY, next === 'force-collapsed' ? 'true' : 'false');
    }
  };

  // Потребность по роли исполнителя: часы РП идут в пул РП, не аналитика
  const roleDemand = useMemo(() => {
    if (!allocations) return { analyst: 0, dev: 0, qa: 0 };
    return employees && employees.length > 0
      ? demandByAssigneeRole(allocations, employees)
      : demandByRole(allocations);
  }, [allocations, employees]);

  // Измеренные высоты двух вариантов — для плавной height-анимации.
  // Оба варианта рендерятся одновременно (один невидимый), но крайне дёшево:
  // ~40 DOM-узлов суммарно, замеряем через ResizeObserver чтобы реагировать
  // на смену состава ролей/сотрудников.
  const expandedRef = useRef<HTMLDivElement>(null);
  const collapsedRef = useRef<HTMLDivElement>(null);
  const [heights, setHeights] = useState<{ full: number; collapsed: number }>({ full: 0, collapsed: 0 });

  useLayoutEffect(() => {
    if (!expandedRef.current || !collapsedRef.current) return;
    const measure = () => {
      const full = expandedRef.current?.offsetHeight ?? 0;
      const col = collapsedRef.current?.offsetHeight ?? 0;
      heightsRef.current = { full, collapsed: col };
      setHeights((prev) => (prev.full === full && prev.collapsed === col ? prev : { full, collapsed: col }));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(expandedRef.current);
    ro.observe(collapsedRef.current);
    return () => ro.disconnect();
  }, [summary, allocations, employees, roles]);

  if (isLoading) {
    return (
      <Card styles={{ body: { padding: 14 } }}>
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (!summary || summary.roles.length === 0) return null;

  const collapsedTotalDemand = Object.values(roleDemand).reduce((s, v) => s + v, 0);
  const collapsedTotalRemaining = Math.round(summary.available_for_backlog_total - collapsedTotalDemand);
  const collapsedTotalDeficit = collapsedTotalRemaining < 0;

  // Фиксированные ширины крайних колонок + minmax(0, 1fr) на ролевые: гарантирует,
  // что колонки выравниваются между независимыми сетками строк (max-content
  // по содержимому давал расхождение между строкой шапки и «На бэклог»).
  const gridCols = `300px repeat(${summary.roles.length}, minmax(0, 1fr)) 140px`;

  const roleBorderStyle = (role: string): React.CSSProperties => {
    const color = getRoleColor(roles, role);
    const isLast = role === summary.roles[summary.roles.length - 1];
    return {
      borderLeft: `2px solid ${color}`,
      ...(isLast ? { borderRight: `2px solid ${color}` } : {}),
    };
  };

  const roleCellStyle = (role: string): React.CSSProperties => {
    const color = getRoleColor(roles, role);
    const isLast = role === summary.roles[summary.roles.length - 1];
    return {
      borderLeft: `2px solid ${color}`,
      ...(isLast ? { borderRight: `2px solid ${color}` } : {}),
      background: `${color}08`,
    };
  };

  const headerStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: gridCols,
    gap: 1,
    background: DARK_THEME.border,
    borderRadius: '6px 6px 0 0',
    overflow: 'hidden',
  };

  const rowStyle = (opts?: { borderTop?: string }): React.CSSProperties => ({
    display: 'grid',
    gridTemplateColumns: gridCols,
    gap: 1,
    background: DARK_THEME.border,
    borderTop: opts?.borderTop ?? ROW_DIVIDER,
  });

  const totalDemand = Object.values(roleDemand).reduce((s, v) => s + v, 0);

  const collapsedCard = (
    <Card styles={{ body: { padding: 0, overflow: 'hidden' } }}>
      <div style={{ display: 'flex', alignItems: 'center', height: 40 }}>
        <div style={{
          padding: '0 14px',
          fontSize: 12,
          color: DARK_THEME.textMuted,
          borderRight: `1px solid ${DARK_THEME.border}`,
          background: DARK_THEME.darkAccent,
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          whiteSpace: 'nowrap' as const,
        }}>
          На бэклог
        </div>
        {summary.roles.map((role) => {
          const avail = summary.available_for_backlog_by_role[role] ?? 0;
          const used = roleDemand[role as keyof typeof roleDemand] ?? 0;
          const remaining = Math.round(avail - used);
          const isDeficit = remaining < 0;
          const hasUsed = used > 0;
          return (
            <div key={role} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '0 16px',
              borderRight: `1px solid ${DARK_THEME.border}`,
              height: '100%',
            }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: getRoleColor(roles, role) }}>
                {getRoleLabel(roles, role)}
              </span>
              <span
                className={pulsedRoles?.has(role) ? 'role-pulse' : undefined}
                style={{ fontSize: 14, fontWeight: 700, fontFamily: FONTS.mono, color: isDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary }}
              >
                {hasUsed ? remaining : Math.round(avail)} ч
              </span>
            </div>
          );
        })}
        <div style={{
          padding: '0 16px',
          borderRight: `1px solid ${DARK_THEME.border}`,
          height: '100%',
          display: 'flex',
          alignItems: 'center',
        }}>
          <span style={{ fontSize: 15, fontWeight: 700, fontFamily: FONTS.mono, color: collapsedTotalDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary }}>
            {collapsedTotalDemand > 0 ? collapsedTotalRemaining : Math.round(summary.available_for_backlog_total)} ч
          </span>
        </div>
        <button
          onClick={toggleCollapsed}
          style={{
            marginLeft: 'auto',
            padding: '0 14px',
            height: '100%',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: 11,
            color: DARK_THEME.textMuted,
          }}
        >
          ↓ Развернуть
        </button>
      </div>
    </Card>
  );

  const expandedCard = (
    <Card styles={{ body: { padding: 0, overflow: 'hidden', borderRadius: 8 } }}>
      <div style={{ display: 'flex', alignItems: 'stretch' }}>
        {/* Основная таблица */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Кнопка свернуть — всегда над таблицей */}
          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            padding: '4px 10px',
            borderBottom: `1px solid ${DARK_THEME.border}`,
            background: DARK_THEME.cardBg,
          }}>
            <button
              onClick={toggleCollapsed}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: 11,
                color: DARK_THEME.textMuted,
                padding: '2px 4px',
              }}
            >
              ↑ Свернуть
            </button>
          </div>
          {/* Header row */}
          <div style={headerStyle}>
            <div style={{ ...CELL_LABEL, background: DARK_THEME.darkAccent }} />
            {summary.roles.map((role) => {
              const names = summary.role_employee_names[role] ?? [];
              const label = getRoleLabel(roles, role);
              return (
                <Tooltip
                  key={role}
                  title={
                    names.length > 0 ? (
                      <div>{names.map((n) => <div key={n}>{n}</div>)}</div>
                    ) : 'Нет сотрудников'
                  }
                >
                  <div
                    style={{
                      ...CELL,
                      ...roleCellStyle(role),
                      textAlign: 'center',
                      color: DARK_THEME.textSecondary,
                      cursor: 'default',
                      paddingTop: 10,
                      paddingLeft: 4,
                      paddingRight: 4,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'baseline',
                        justifyContent: 'center',
                        gap: 4,
                        whiteSpace: 'nowrap' as const,
                      }}
                    >
                      <span
                        style={{
                          fontWeight: 600,
                          fontSize: 13,
                          color: getRoleColor(roles, role),
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {label}
                      </span>
                      <span style={{ fontSize: 10, color: DARK_THEME.textHint, flexShrink: 0 }}>
                        · {names.length}
                      </span>
                    </div>
                    <div
                      style={{
                        height: 3,
                        background: getRoleColor(roles, role),
                        borderRadius: 2,
                        margin: '4px auto',
                        width: '80%',
                      }}
                    />
                  </div>
                </Tooltip>
              );
            })}
            <div
              style={{
                ...CELL,
                background: DARK_THEME.darkAccent,
                textAlign: 'center',
                color: DARK_THEME.textMuted,
                fontWeight: 600,
              }}
            >
              Итого
            </div>
          </div>

          {/* Нормированные работы */}
          <div style={rowStyle({ borderTop: 'none' })}>
            <div style={{ ...CELL_LABEL, background: DARK_THEME.cardBg, fontWeight: 600, color: DARK_THEME.textPrimary, whiteSpace: 'nowrap' as const }}>
              Нормированные работы
            </div>
            {summary.roles.map((role) => (
              <div key={role} style={{ ...CELL, ...roleCellStyle(role), fontWeight: 600 }}>
                {Math.round(summary.total_by_role[role] ?? 0).toLocaleString('ru')}
              </div>
            ))}
            <div style={{ ...CELL, background: DARK_THEME.cardBg, fontWeight: 700, color: DARK_THEME.textPrimary }}>
              {Math.round(summary.total).toLocaleString('ru')}
            </div>
          </div>

          {/* Обязательные работы */}
          {summary.work_type_rows.map((row) => (
            <div key={row.work_type_id} style={rowStyle()}>
              <div
                style={{
                  ...CELL_LABEL,
                  background: DARK_THEME.darkAccent,
                  whiteSpace: 'nowrap' as const,
                }}
              >
                — {row.work_type_label}
              </div>
              {summary.roles.map((role) => {
                const h = row.by_role[role] ?? 0;
                const pct = row.by_role_pct[role];
                return (
                  <div key={role} style={{ ...CELL, ...roleCellStyle(role), color: DARK_THEME.textMuted }}>
                    {h > 0 ? Math.round(h).toLocaleString('ru') : '—'}
                    {pct != null && h > 0 && (
                      <span style={{ marginLeft: 4, fontSize: 10, color: DARK_THEME.textHint }}>
                        {pct}%
                      </span>
                    )}
                  </div>
                );
              })}
              <div style={{ ...CELL, background: DARK_THEME.darkAccent, color: DARK_THEME.textMuted }}>
                {Math.round(row.total).toLocaleString('ru')}
              </div>
            </div>
          ))}

          {/* На бэклог */}
          <div style={{ ...rowStyle({ borderTop: `2px solid ${DARK_THEME.cyanPrimary}` }) }}>
            <div
              style={{
                ...CELL_LABEL,
                background: 'rgba(0,201,200,0.08)',
                color: DARK_THEME.cyanPrimary,
                fontWeight: 700,
                fontSize: 16,
                boxShadow: `inset 2px 0 0 ${DARK_THEME.cyanPrimary}`,
                whiteSpace: 'nowrap' as const,
              }}
            >
              На бэклог
            </div>
            {summary.roles.map((role) => {
              const avail = summary.available_for_backlog_by_role[role] ?? 0;
              const used = roleDemand[role as keyof typeof roleDemand] ?? 0;
              const remaining = Math.round(avail - used);
              const isDeficit = remaining < 0;
              const isExternal = role === 'qa' && summary.external_qa_hours != null;
              const hasUsed = used > 0;
              const utilPct = avail > 0 ? Math.min(150, (used / avail) * 100) : 0;
              const barColor =
                utilPct > 110 ? '#f5222d' :
                utilPct > 100 ? '#fa8c16' :
                DARK_THEME.cyanPrimary;
              return (
                <div
                  key={role}
                  style={{
                    ...CELL,
                    ...roleBorderStyle(role),
                    background: isDeficit ? 'rgba(255,165,0,0.08)' : 'rgba(0,201,200,0.1)',
                    color: isDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
                    fontWeight: 700,
                    fontSize: 17,
                    whiteSpace: 'nowrap' as const,
                    position: 'relative' as const,
                    paddingBottom: 12,
                  }}
                >
                  <span className={pulsedRoles?.has(role) ? 'role-pulse' : undefined}>
                    {hasUsed ? (
                      <>
                        {remaining.toLocaleString('ru')}
                        <span style={{ fontSize: 12, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
                          из {Math.round(avail).toLocaleString('ru')}
                        </span>
                      </>
                    ) : (
                      Math.round(avail).toLocaleString('ru')
                    )}
                  </span>
                  {isExternal && (
                    <span style={{ fontSize: 11, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
                      внешний
                    </span>
                  )}
                  {hasUsed && (
                    <div
                      style={{
                        position: 'absolute',
                        bottom: 4,
                        left: 8,
                        right: 8,
                        height: 4,
                        background: 'rgba(255,255,255,0.06)',
                        borderRadius: 2,
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          position: 'absolute',
                          inset: 0,
                          transform: `scaleX(${Math.min(100, utilPct) / 100})`,
                          transformOrigin: 'left',
                          background: barColor,
                          transition: 'transform 0.3s ease, background-color 0.3s ease',
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
            {(() => {
              const totalRemaining = Math.round(summary.available_for_backlog_total - totalDemand);
              const isTotalDeficit = totalRemaining < 0;
              return (
                <div
                  style={{
                    ...CELL,
                    background: isTotalDeficit ? 'rgba(255,165,0,0.08)' : 'rgba(0,201,200,0.08)',
                    color: isTotalDeficit ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
                    fontWeight: 700,
                    fontSize: 17,
                    whiteSpace: 'nowrap' as const,
                  }}
                >
                  {totalDemand > 0 ? (
                    <>
                      {totalRemaining.toLocaleString('ru')}
                      <span style={{ fontSize: 12, color: DARK_THEME.textHint, fontWeight: 400, marginLeft: 6 }}>
                        из {Math.round(summary.available_for_backlog_total).toLocaleString('ru')}
                      </span>
                    </>
                  ) : (
                    Math.round(summary.available_for_backlog_total).toLocaleString('ru')
                  )}
                </div>
              );
            })()}
          </div>
        </div>

        {/* Блок отсутствий */}
        {summary.absence_days_by_employee.length > 0 && (() => {
          const totalUnplanned = summary.absence_days_by_employee.reduce(
            (s, e) => s + e.unplanned_days, 0,
          );
          const showUnplannedCol = totalUnplanned > 0;
          return (
          <div style={{
            borderLeft: `2px solid ${DARK_THEME.border}`,
            background: DARK_THEME.darkAccent,
            minWidth: showUnplannedCol ? 230 : 180,
            maxWidth: showUnplannedCol ? 290 : 240,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
          }}>
            {/* Заголовок */}
            <div style={{
              padding: '8px 12px',
              borderBottom: `1px solid ${DARK_THEME.border}`,
              fontSize: 10,
              color: DARK_THEME.textMuted,
              textTransform: 'uppercase' as const,
              letterSpacing: 0.5,
              fontWeight: 600,
              background: DARK_THEME.cardBg,
            }}>
              Отсутствия квартала
            </div>
            {/* Подзаголовок-легенда */}
            <div style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 12,
              padding: '4px 12px 2px',
              fontSize: 9,
              color: DARK_THEME.textHint,
              textTransform: 'uppercase' as const,
              letterSpacing: 0.4,
            }}>
              <span style={{ width: 36, textAlign: 'right' as const }}>отпуск</span>
              {showUnplannedCol && <span style={{ width: 36, textAlign: 'right' as const }}>прочее</span>}
            </div>
            {/* Список сотрудников */}
            <div style={{ padding: '2px 12px 6px', flex: 1 }}>
              {summary.absence_days_by_employee.map((emp) => {
                const roleColor = emp.role ? getRoleColor(roles, emp.role) : DARK_THEME.textDim;
                return (
                  <div key={emp.employee_id} style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 8,
                    padding: '3px 0',
                    borderBottom: `1px solid rgba(255,255,255,0.04)`,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flex: 1 }}>
                      <div style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: roleColor,
                        flexShrink: 0,
                      }} />
                      <span style={{
                        fontSize: 11,
                        color: DARK_THEME.textSecondary,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap' as const,
                      }}>
                        {emp.display_name}
                      </span>
                    </div>
                    <span style={{
                      fontSize: 11,
                      fontFamily: FONTS.mono,
                      color: emp.planned_days > 0 ? DARK_THEME.textSecondary : DARK_THEME.textDim,
                      width: 36,
                      textAlign: 'right' as const,
                      flexShrink: 0,
                    }}>
                      {emp.planned_days > 0 ? `${emp.planned_days} дн` : '—'}
                    </span>
                    {showUnplannedCol && (
                      <span style={{
                        fontSize: 11,
                        fontFamily: FONTS.mono,
                        color: emp.unplanned_days > 0 ? DARK_THEME.textSecondary : DARK_THEME.textDim,
                        width: 36,
                        textAlign: 'right' as const,
                        flexShrink: 0,
                      }}>
                        {emp.unplanned_days > 0 ? `${emp.unplanned_days} дн` : '—'}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            {/* Итого */}
            {(() => {
              const totalPlanned = summary.absence_days_by_employee.reduce((s, e) => s + e.planned_days, 0);
              const totalUnpl = summary.absence_days_by_employee.reduce((s, e) => s + e.unplanned_days, 0);
              const totalAbsHours = Math.round(
                Object.values(summary.calendar_gross_by_role).reduce((s, v) => s + v, 0) -
                Object.values(summary.total_by_role).reduce((s, v) => s + v, 0)
              );
              return (totalPlanned + totalUnpl) > 0 ? (
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 12px',
                  borderTop: `1px solid ${DARK_THEME.border}`,
                  fontSize: 11,
                }}>
                  <span style={{ color: DARK_THEME.textMuted, flex: 1 }}>
                    Итого
                    <span style={{ marginLeft: 6, color: DARK_THEME.textHint, fontFamily: FONTS.mono }}>
                      −{totalAbsHours} ч
                    </span>
                  </span>
                  <span style={{
                    fontFamily: FONTS.mono,
                    color: DARK_THEME.textSecondary,
                    width: 36,
                    textAlign: 'right' as const,
                    flexShrink: 0,
                  }}>
                    {totalPlanned} дн
                  </span>
                  {showUnplannedCol && (
                    <span style={{
                      fontFamily: FONTS.mono,
                      color: DARK_THEME.textSecondary,
                      width: 36,
                      textAlign: 'right' as const,
                      flexShrink: 0,
                    }}>
                      {totalUnpl} дн
                    </span>
                  )}
                </div>
              ) : null;
            })()}
          </div>
          );
        })()}
      </div>
    </Card>
  );

  // Высота анимируется через explicit `height` на внешнем wrapper.
  // Пока обе высоты ещё не измерены — fallback на auto, чтобы первый paint
  // не был с нулевой высотой. После первого useLayoutEffect — измеренная.
  const measured = heights.full > 0 && heights.collapsed > 0;
  // Высота sticky-элемента анимируется между измеренными значениями.
  // Контент ниже sticky естественно подтягивается за сжимающимся слотом —
  // никакой spacer не нужен; плавность даёт длительность + material-easing.
  const innerHeight = !measured ? undefined : (collapsed ? heights.collapsed : heights.full);
  // Мягкое замедление в конце (ease-out квадратичная) и подобранная длительность
  // ~0.8с — чтобы сжатие/расширение блока ощущалось плавно и нижняя таблица
  // (Элементы бэклога) подтягивалась без резкого скачка.
  const EASE = 'cubic-bezier(0.25, 0.1, 0.25, 1)';
  const DUR = '0.8s';

  return (
    <>
      <div ref={setSentinelEl} aria-hidden style={{ height: 1, marginBottom: -1 }} />
    <div
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 20,
        height: innerHeight,
        overflow: 'hidden',
        transition: `height ${DUR} ${EASE}, box-shadow .2s ease`,
        boxShadow: isStuck ? '0 6px 16px rgba(0,0,0,0.45)' : 'none',
      }}
    >
      <div
        ref={expandedRef}
        style={{
          // До первого замера — обычный flow (intrinsic высота даёт измерение).
          // После замера — absolute, обе варианта стэкаются.
          position: measured ? 'absolute' : 'relative',
          top: 0,
          left: 0,
          right: 0,
          opacity: collapsed ? 0 : 1,
          transition: `opacity ${DUR} ${EASE}`,
          pointerEvents: collapsed ? 'none' : 'auto',
        }}
        aria-hidden={collapsed}
      >
        {expandedCard}
      </div>
      <div
        ref={collapsedRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          opacity: collapsed ? 1 : 0,
          transition: `opacity ${DUR} ${EASE}`,
          pointerEvents: collapsed ? 'auto' : 'none',
          // До первого замера прячем — иначе мерцает поверх expandedCard.
          visibility: measured ? 'visible' : 'hidden',
        }}
        aria-hidden={!collapsed}
      >
        {collapsedCard}
      </div>
    </div>
    </>
  );
}

const ScenarioResourceSummary = memo(ScenarioResourceSummaryBase);
export default ScenarioResourceSummary;
