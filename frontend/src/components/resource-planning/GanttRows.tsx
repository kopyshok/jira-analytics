import { useEffect, useMemo, useState } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';
import type { EmployeeResponse } from '../../types/api';
import type { GanttTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth, PHASE_COLORS, PHASE_LABELS, getItemColor } from '../../utils/gantt';
import EmployeeAvatar from './EmployeeAvatar';
import { usePatchAssignment } from '../../hooks/useResourcePlanning';
import { useAppearanceSettings } from '../../contexts/AppearanceContext';
import { useRpPreferences } from '../../hooks/useRpPreferences';
import { computeFillGradientAlphas } from './AppearanceModal';

export type ViewMode = 'portfolio' | 'two-level' | 'resource-track' | 'plane';

interface Props {
  assignments: AssignmentOut[];
  timeline: GanttTimeline;
  viewMode: ViewMode;
  leftColWidth: number;
  trackWidthPx?: number;
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  planId: string;
  employees: EmployeeResponse[];
  depDrawMode?: boolean;
  pendingFromItem?: string | null;
  onItemClick?: (itemId: string) => void;
  collapsedItemIds?: string[];
  onToggleCollapse?: (itemId: string, collapsed: boolean) => void;
  conflictAssignmentIds?: string[];
  onAssignmentClick?: (assignmentId: string) => void;
  highlightedEmployeeId?: string | null;
  onEmployeeRowClick?: (employeeId: string | null) => void;
}

type SubProps = Omit<Props, 'viewMode'>;

const trackStyle = (trackWidthPx?: number): React.CSSProperties =>
  trackWidthPx
    ? { width: trackWidthPx, flex: '0 0 auto', position: 'relative' }
    : { flex: 1, position: 'relative' };

const ROW_HEIGHT = 36;
const JIRA_BASE = 'https://itgri.atlassian.net';
const ROW_BG = 'transparent';
const INIT_HEADER_BG = 'rgba(0,201,200,0.20)';
const INIT_PENDING_BG = 'rgba(255,122,69,0.22)';
const INIT_DIVIDER = '2px solid #066770';
// Opaque blends of INIT_HEADER_BG / INIT_PENDING_BG over pageBg #0d1c33 — used on
// sticky left-column wrappers so absolute bars/markers don't bleed through during horizontal scroll.
// Must visually match the translucent tints above when rendered over #0d1c33.
const INIT_HEADER_BG_OPAQUE = '#0a3f51';
const PENDING_FROM_BG_OPAQUE = '#423137';
// Sticky left-column z-index must exceed overlay layers (today marker z=20, OoQ divider z=19).
const STICKY_CELL_Z = 25;
const STICKY_INIT_Z = 26;

// Зеркало backend ANALYST_ROLES / DEV_ROLES — нужно для разделения ОПЭ на 2 строки.
const ANALYST_ROLE_CODES = new Set([
  'аналитик', 'analyst', 'an',
  'рп', 'rp',
  'консультант', 'consultant',
]);
const DEV_ROLE_CODES = new Set(['разработчик', 'developer', 'dev', 'программист']);

function ItemTitleCell({
  title, jiraKey, priority, leftColWidth, fontWeight = 600,
  dotColor, assignee, hours, bg = '#0a1628',
}: {
  title: string; jiraKey: string | null; priority?: number | null;
  leftColWidth: number; fontWeight?: number;
  dotColor?: string;
  assignee?: React.ReactNode; hours?: React.ReactNode;
  bg?: string;
}) {
  const titleNode = (
    <span
      style={{
        fontSize: 13,
        lineHeight: 1.3,
        wordBreak: 'break-word',
        overflow: 'hidden',
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
      } as React.CSSProperties}
    >
      {title}
      {hours && (
        <span style={{ color: '#8ab0d8', fontWeight: 400, marginLeft: 6, fontSize: 11 }}>
          · {hours}
        </span>
      )}
    </span>
  );
  return (
    <div style={{
      width: leftColWidth,
      flexShrink: 0,
      borderRight: '1px solid #1e3a5f',
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 1fr) 160px',
      columnGap: 8,
      alignItems: 'center',
      padding: '6px 12px',
      fontSize: 13,
      fontWeight,
      color: '#fff',
      overflow: 'hidden',
      position: 'sticky',
      left: 0,
      zIndex: STICKY_CELL_Z,
      background: bg,
      // Extend opaque coverage below cell to cover SVG arrows (z=10) in row gaps.
      // 1px = subrow borderBottom (#0e2540); +2px = init divider (#066770) for last subrow before next initiative.
      // Middle subrows: next subrow's sticky cell (z=25, after in DOM) overlays the extra 2px → no visual bleed.
      boxShadow: '0 1px 0 0 #0e2540, 0 3px 0 0 #066770',
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, overflow: 'hidden' }}>
        {jiraKey && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {priority != null && (
              <span
                title={`Приоритет: ${priority}`}
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: '#0d1c33',
                  background: '#00c9c8',
                  borderRadius: 3,
                  padding: '0 5px',
                  minWidth: 16,
                  textAlign: 'center',
                  lineHeight: '14px',
                }}
              >
                {priority}
              </span>
            )}
            <a
              href={`${JIRA_BASE}/browse/${jiraKey}`}
              target="_blank"
              rel="noreferrer"
              onClick={e => e.stopPropagation()}
              style={{ fontSize: 10, color: '#7a9ab8', textDecoration: 'none', letterSpacing: 0.3 }}
            >
              {jiraKey}
            </a>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, overflow: 'hidden' }}>
          {dotColor && (
            <span
              style={{
                width: 8, height: 8,
                borderRadius: 2,
                background: dotColor,
                flexShrink: 0,
                marginTop: 5,
                display: 'inline-block',
              }}
            />
          )}
          {titleNode}
        </div>
      </div>
      <div style={{ fontSize: 11, color: '#8ab0d8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {assignee ?? ''}
      </div>
    </div>
  );
}

function PortfolioRows({ assignments, timeline, leftColWidth, trackWidthPx, rowRefs, onAssignmentClick }: SubProps) {
  const byItem = useMemo(() => {
    const map = new Map<string, { title: string; key: string | null; priority: number | null; assignments: AssignmentOut[] }>();
    for (const a of assignments) {
      if (!map.has(a.backlog_item_id)) {
        map.set(a.backlog_item_id, {
          title: a.backlog_item_title,
          key: a.backlog_item_key,
          priority: a.priority ?? null,
          assignments: [],
        });
      }
      map.get(a.backlog_item_id)!.assignments.push(a);
    }
    return [...map.entries()];
  }, [assignments]);

  return (
    <>
      {byItem.map(([itemId, { title, key, priority, assignments: itemAssignments }]) => (
        <div
          key={itemId}
          ref={el => {
            if (el) rowRefs.current.set(itemId, el);
            else rowRefs.current.delete(itemId);
          }}
          style={{
            display: 'flex',
            minHeight: ROW_HEIGHT,
            borderBottom: '1px solid #0e2540',
            background: ROW_BG,
          }}
        >
          <ItemTitleCell title={title} jiraKey={key} priority={priority} leftColWidth={leftColWidth} />
          <div style={trackStyle(trackWidthPx)}>
            {itemAssignments.filter(a => a.start_date && a.end_date).map(a => {
              const left = dateToLeft(a.start_date!, timeline);
              const width = datesToWidth(a.start_date!, a.end_date!, timeline);
              const color = PHASE_COLORS[a.phase] ?? '#888';
              return (
                <div
                  key={a.id}
                  title={`${PHASE_LABELS[a.phase]} — ${a.employee_name ?? '—'} (${a.hours_allocated?.toFixed(0)}ч)`}
                  onClick={(e) => {
                    if (a.phase === 'qa') return;
                    e.stopPropagation();
                    onAssignmentClick?.(a.id);
                  }}
                  style={{
                    position: 'absolute',
                    left: `${left}%`,
                    width: `${width}%`,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    height: 22,
                    background: color,
                    opacity: 0.85,
                    borderRadius: 3,
                    zIndex: 2,
                    display: 'flex',
                    alignItems: 'center',
                    paddingLeft: 4,
                    fontSize: 9,
                    color: '#0d1c33',
                    fontWeight: 700,
                    overflow: 'hidden',
                    whiteSpace: 'nowrap',
                    cursor: a.phase === 'qa' ? 'default' : 'pointer',
                    outline: a.is_pinned ? '1px solid #00c9c8' : 'none',
                    gap: 4,
                  }}
                >
                  {a.phase !== 'qa' && a.employee_name && (
                    <EmployeeAvatar name={a.employee_name} role={a.employee_role} size={16} />
                  )}
                  <span style={{ fontSize: 9 }}>{PHASE_LABELS[a.phase]}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </>
  );
}

interface PhaseBarProps {
  assignment: AssignmentOut;
  planId: string;
  timeline: GanttTimeline;
  refKey: string;
  extraRefKeys?: string[];
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  color: string;
  showResize: boolean;
  employees: EmployeeResponse[];
  hasConflict?: boolean;
  dimmed?: boolean;
  onClick?: () => void;
  unavailableDays?: Array<{ date: string; type: 'weekend' | 'holiday' | 'absence' | 'block' }>;
  highlightedEmployeeId?: string | null;
  pulseEmp?: boolean;
  pulseCp?: boolean;
}

function PhaseBar({ assignment, planId, timeline, refKey, extraRefKeys, rowRefs, color, showResize, hasConflict, dimmed, onClick, unavailableDays, highlightedEmployeeId, pulseEmp, pulseCp }: PhaseBarProps) {
  const patch = usePatchAssignment();
  const [drag, setDrag] = useState<null | {
    mode: 'move' | 'resize-start' | 'resize-end';
    startClientX: number;
    origStart: string;
    origEnd: string;
    rowWidthPx: number;
  }>(null);
  const [previewLeft, setPreviewLeft] = useState<number | null>(null);
  const [previewWidth, setPreviewWidth] = useState<number | null>(null);

  const beginDrag = (e: React.MouseEvent, mode: 'move' | 'resize-start' | 'resize-end') => {
    e.stopPropagation();
    e.preventDefault();
    if (!assignment.start_date || !assignment.end_date) return;
    const row = (e.currentTarget as HTMLElement).closest('[data-gantt-row="true"]') as HTMLElement | null;
    if (!row) return;
    const trackEl = row.querySelector('[data-gantt-track="true"]') as HTMLElement | null;
    const trackWidth = trackEl ? trackEl.getBoundingClientRect().width : row.getBoundingClientRect().width;
    setDrag({
      mode,
      startClientX: e.clientX,
      origStart: assignment.start_date,
      origEnd: assignment.end_date,
      rowWidthPx: trackWidth,
    });
  };

  const computeNewDates = (dxDays: number) => {
    const sd = new Date(drag!.origStart + 'T00:00:00');
    const ed = new Date(drag!.origEnd + 'T00:00:00');
    if (drag!.mode === 'move') {
      sd.setDate(sd.getDate() + dxDays);
      ed.setDate(ed.getDate() + dxDays);
    } else if (drag!.mode === 'resize-start') {
      sd.setDate(sd.getDate() + dxDays);
      if (sd >= ed) sd.setTime(ed.getTime() - 86_400_000);
    } else {
      ed.setDate(ed.getDate() + dxDays);
      if (ed <= sd) ed.setTime(sd.getTime() + 86_400_000);
    }
    const fmt = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    return { newStart: fmt(sd), newEnd: fmt(ed) };
  };

  const onMouseMove = (e: MouseEvent) => {
    if (!drag) return;
    const dxPx = e.clientX - drag.startClientX;
    const pxPerDay = drag.rowWidthPx / timeline.totalDays;
    const dxDays = Math.round(dxPx / pxPerDay);
    if (dxDays === 0) return;
    const { newStart, newEnd } = computeNewDates(dxDays);
    setPreviewLeft(dateToLeft(newStart, timeline));
    setPreviewWidth(datesToWidth(newStart, newEnd, timeline));
  };

  const onMouseUp = (e: MouseEvent) => {
    if (!drag) return;
    const dxPx = e.clientX - drag.startClientX;
    const pxPerDay = drag.rowWidthPx / timeline.totalDays;
    const dxDays = Math.round(dxPx / pxPerDay);
    if (dxDays !== 0) {
      const { newStart, newEnd } = computeNewDates(dxDays);
      patch.mutate({
        planId,
        assignmentId: assignment.id,
        data: { start_date: newStart, end_date: newEnd },
      });
    }
    setDrag(null);
    setPreviewLeft(null);
    setPreviewWidth(null);
  };

  useMemoizedDragListeners(drag, onMouseMove, onMouseUp);

  if (!assignment.start_date || !assignment.end_date) return null;

  const left = dateToLeft(assignment.start_date, timeline);
  const width = datesToWidth(assignment.start_date, assignment.end_date, timeline);

  const isMe = !!highlightedEmployeeId && assignment.employee_id === highlightedEmployeeId;
  const isDimmedByHighlight = !!highlightedEmployeeId && !isMe && assignment.phase !== 'qa';
  const effectiveDimmed = dimmed || isDimmedByHighlight;

  const isOoQ = assignment.out_of_quarter;

  const factPct = assignment.hours_allocated && assignment.worklog_hours_actual
    ? Math.min(1, assignment.worklog_hours_actual / assignment.hours_allocated)
    : 0;

  const barClassName = [
    isMe && pulseEmp ? 'rp-bar-emp-highlighted' : '',
    assignment.is_on_critical_path && pulseCp ? 'rp-bar-critical' : '',
  ].filter(Boolean).join(' ');

  const bar = (
    <div
      ref={el => {
        if (el) {
          rowRefs.current.set(refKey, el);
          extraRefKeys?.forEach(k => rowRefs.current.set(k, el));
        } else {
          rowRefs.current.delete(refKey);
          extraRefKeys?.forEach(k => rowRefs.current.delete(k));
        }
      }}
      onMouseDown={(e) => beginDrag(e, 'move')}
      onClick={(e) => {
        if (drag) return;
        if (onClick) {
          e.stopPropagation();
          onClick();
        }
      }}
      title={`${PHASE_LABELS[assignment.phase]} — ${assignment.hours_allocated?.toFixed(0)}ч`}
      className={barClassName || undefined}
      style={{
        position: 'absolute',
        left: `${left}%`,
        width: `${Math.max(width, 0.8)}%`,
        top: '50%',
        transform: 'translateY(-50%)',
        height: 18,
        background: isOoQ
          ? `repeating-linear-gradient(45deg, ${color} 0 6px, rgba(0,0,0,0.15) 6px 12px)`
          : color,
        opacity: effectiveDimmed ? 0.12 : (isOoQ ? 0.6 : 1),
        borderRadius: 3,
        border: isOoQ
          ? '1px solid #ffb432'
          : assignment.is_on_critical_path
            ? '1px solid #e85d4a'
            : 'none',
        boxShadow: hasConflict
          ? 'inset 0 0 0 2px #ef4444'
          : isMe
            ? '0 0 8px rgba(0,201,200,0.7)'
            : (assignment.is_on_critical_path && !pulseCp)
              ? '0 0 6px rgba(232,93,74,0.5)'
              : 'none',
        outline: isMe ? '2px solid #00c9c8' : (assignment.is_pinned ? '1px solid #00c9c8' : 'none'),
        zIndex: 2,
        cursor: assignment.phase === 'qa' ? 'default' : 'grab',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      {factPct > 0 && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: `${factPct * 100}%`,
            background: 'rgba(255,255,255,0.30)',
            borderRadius: '3px 0 0 3px',
            pointerEvents: 'none',
            zIndex: 1,
          }}
        />
      )}
      {assignment.worklog_hours_actual > (assignment.hours_allocated ?? 0) && assignment.hours_allocated && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            border: '1.5px solid #ef4444',
            borderRadius: 3,
            pointerEvents: 'none',
            zIndex: 2,
          }}
        />
      )}
      {unavailableDays && unavailableDays.length > 0 && (
        <UnavailabilityOverlay
          start={assignment.start_date}
          end={assignment.end_date}
          days={unavailableDays}
        />
      )}
    </div>
  );

  return (
    <>
      {bar}
      {showResize && (
        <>
          <div
            onMouseDown={(e) => beginDrag(e, 'resize-start')}
            style={{
              position: 'absolute',
              top: '50%',
              transform: 'translateY(-50%)',
              left: `calc(${left}% - 3px)`,
              width: 6,
              height: 22,
              cursor: 'ew-resize',
              background: 'transparent',
              zIndex: 4,
            }}
          />
          <div
            onMouseDown={(e) => beginDrag(e, 'resize-end')}
            style={{
              position: 'absolute',
              top: '50%',
              transform: 'translateY(-50%)',
              left: `calc(${left + width}% - 3px)`,
              width: 6,
              height: 22,
              cursor: 'ew-resize',
              background: 'transparent',
              zIndex: 4,
            }}
          />
        </>
      )}
      {previewLeft !== null && previewWidth !== null && (
        <div
          style={{
            position: 'absolute',
            left: `${previewLeft}%`,
            width: `${previewWidth}%`,
            top: '50%',
            transform: 'translateY(-50%)',
            height: 22,
            background: color,
            opacity: 0.4,
            borderRadius: 3,
            outline: '1px dashed #fff',
            zIndex: 5,
            pointerEvents: 'none',
          }}
        />
      )}
    </>
  );
}

interface UnavailabilityOverlayProps {
  start: string | null;
  end: string | null;
  days: Array<{ date: string; type: 'weekend' | 'holiday' | 'absence' | 'block' }>;
}

function UnavailabilityOverlay({ start, end, days }: UnavailabilityOverlayProps) {
  if (!start || !end || days.length === 0) return null;
  const startTs = new Date(start + 'T00:00:00').getTime();
  const endTs = new Date(end + 'T00:00:00').getTime();
  const totalDays = Math.max(1, Math.round((endTs - startTs) / 86_400_000) + 1);
  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', display: 'flex' }}>
      {days.map(d => {
        const ts = new Date(d.date + 'T00:00:00').getTime();
        const offset = Math.max(0, Math.round((ts - startTs) / 86_400_000));
        const left = (offset / totalDays) * 100;
        const width = (1 / totalDays) * 100;
        let bg: string;
        if (d.type === 'absence' || d.type === 'block') {
          bg = 'repeating-linear-gradient(45deg, rgba(239,68,68,0.60) 0 4px, rgba(239,68,68,0.30) 4px 8px)';
        } else if (d.type === 'holiday') {
          bg = 'repeating-linear-gradient(45deg, rgba(245,158,11,0.55) 0 4px, rgba(245,158,11,0.22) 4px 8px)';
        } else {
          bg = 'repeating-linear-gradient(45deg, rgba(0,0,0,0.35) 0 4px, rgba(255,255,255,0.05) 4px 8px)';
        }
        return (
          <div
            key={d.date + d.type}
            style={{
              position: 'absolute',
              left: `${left}%`,
              width: `${width}%`,
              top: 0,
              bottom: 0,
              background: bg,
            }}
          />
        );
      })}
    </div>
  );
}

function useMemoizedDragListeners(
  drag: unknown,
  onMove: (e: MouseEvent) => void,
  onUp: (e: MouseEvent) => void,
) {
  useEffect(() => {
    if (!drag) return;
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [drag, onMove, onUp]);
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  if (clean.length === 3) {
    return [
      parseInt(clean[0] + clean[0], 16),
      parseInt(clean[1] + clean[1], 16),
      parseInt(clean[2] + clean[2], 16),
    ];
  }
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

function TwoLevelRows({
  assignments, timeline, leftColWidth, trackWidthPx, rowRefs, planId, employees,
  depDrawMode, pendingFromItem, onItemClick,
  collapsedItemIds, onToggleCollapse, conflictAssignmentIds, onAssignmentClick,
  highlightedEmployeeId, onEmployeeRowClick,
}: SubProps) {
  const appearance = useAppearanceSettings();
  const { prefs: rpPrefs } = useRpPreferences();
  const collapsedSet = useMemo(() => new Set(collapsedItemIds ?? []), [collapsedItemIds]);
  const conflictSet = useMemo(() => new Set(conflictAssignmentIds ?? []), [conflictAssignmentIds]);
  const byItem = useMemo(() => {
    const map = new Map<string, { title: string; key: string | null; priority: number | null; assignments: AssignmentOut[] }>();
    for (const a of assignments) {
      if (!map.has(a.backlog_item_id)) {
        map.set(a.backlog_item_id, {
          title: a.backlog_item_title,
          key: a.backlog_item_key,
          priority: a.priority ?? null,
          assignments: [],
        });
      }
      map.get(a.backlog_item_id)!.assignments.push(a);
    }
    return [...map.entries()];
  }, [assignments]);

  return (
    <>
      {byItem.map(([itemId, { title, key, priority, assignments: ia }], itemIdx) => {
        const phases = ['analyst', 'dev', 'qa', 'opo'] as const;
        const itemBg = ROW_BG;
        const isPendingFrom = pendingFromItem === itemId;
        const isCollapsed = collapsedSet.has(itemId);

        const totalHours = ia.reduce((s, a) => s + (a.hours_allocated ?? 0), 0);
        const initAssigneeName = ia[0]?.scenario_assignee_name
          ?? ia.find(a => a.phase === 'analyst')?.employee_name
          ?? '—';

        return (
          <div key={itemId} style={{ background: itemBg, borderTop: itemIdx > 0 ? INIT_DIVIDER : 'none' }}>
            <div
              ref={el => {
                if (el) rowRefs.current.set(itemId, el);
                else rowRefs.current.delete(itemId);
              }}
              onClick={() => onItemClick?.(itemId)}
              style={{
                display: 'flex',
                minHeight: ROW_HEIGHT,
                borderBottom: '1px solid #1e3a5f',
                background: isPendingFrom ? INIT_PENDING_BG : INIT_HEADER_BG,
                cursor: depDrawMode ? 'crosshair' : 'default',
                outline: isPendingFrom ? '2px solid #ff7a45' : 'none',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  flexShrink: 0,
                  position: 'sticky',
                  left: 0,
                  zIndex: STICKY_INIT_Z,
                  background: isPendingFrom ? PENDING_FROM_BG_OPAQUE : INIT_HEADER_BG_OPAQUE,
                  boxShadow: '0 1px 0 0 #1e3a5f',
                }}
              >
                <button
                  type="button"
                  aria-label={`${isCollapsed ? 'Развернуть' : 'Свернуть'} ${key ?? title}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleCollapse?.(itemId, !isCollapsed);
                  }}
                  style={{
                    flexShrink: 0,
                    width: 24,
                    background: 'none',
                    border: 0,
                    color: '#7a9ab8',
                    cursor: 'pointer',
                    fontSize: 11,
                    padding: 0,
                  }}
                >
                  {isCollapsed ? '▶' : '▼'}
                </button>
                <ItemTitleCell
                  title={title}
                  jiraKey={key}
                  priority={priority}
                  leftColWidth={leftColWidth - 24}
                  fontWeight={700}
                  assignee={initAssigneeName}
                  hours={totalHours > 0 ? `${Math.round(totalHours)} ч` : ''}
                  bg={isPendingFrom ? PENDING_FROM_BG_OPAQUE : INIT_HEADER_BG_OPAQUE}
                />
              </div>
              <div style={trackStyle(trackWidthPx)}>
                {(() => {
                  const starts = ia.filter(a => a.start_date).map(a => a.start_date!).sort();
                  const ends = ia.filter(a => a.end_date).map(a => a.end_date!).sort();
                  if (!starts[0] || !ends.at(-1)) return null;
                  const left = dateToLeft(starts[0], timeline);
                  const width = datesToWidth(starts[0], ends.at(-1)!, timeline);
                  const BRACKET_COLOR = appearance.initiative_bracket_color;
                  const [br, bg, bb] = hexToRgb(BRACKET_COLOR);
                  const { alphaTop, alphaBottom } = computeFillGradientAlphas(
                    rpPrefs.fill_intensity_pct,
                    rpPrefs.fill_contrast_pct,
                  );
                  const fillGradient = `linear-gradient(180deg, rgba(${br},${bg},${bb},${alphaTop}), rgba(${br},${bg},${bb},${alphaBottom}))`;
                  const animSpeed = appearance.animation_speed_seconds;
                  const BAR_H = 22;
                  return (
                    <div style={{
                      position: 'absolute',
                      left: `${left}%`,
                      width: `${width}%`,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      height: BAR_H,
                      zIndex: 2,
                      pointerEvents: 'none',
                      background: fillGradient,
                    }}>
                      <svg
                        width="100%"
                        height={BAR_H}
                        preserveAspectRatio="none"
                        style={{ position: 'absolute', top: 0, left: 0, overflow: 'visible' }}
                      >
                        <line x1="0" y1="1" x2="100%" y2="1"
                          stroke={BRACKET_COLOR} strokeWidth="1.5" strokeDasharray="6 4"
                          className="rp-init-ants"
                          style={{ animationDuration: `${animSpeed}s` }}
                        />
                        <line x1="0" y1={BAR_H - 1} x2="100%" y2={BAR_H - 1}
                          stroke={BRACKET_COLOR} strokeWidth="1.5" strokeDasharray="6 4"
                          className="rp-init-ants-rev"
                          style={{ animationDuration: `${animSpeed}s` }}
                        />
                      </svg>
                      <div style={{
                        position: 'absolute', left: 0, top: 0, width: 8, height: BAR_H,
                        borderLeft: `2px solid ${BRACKET_COLOR}`,
                        borderTop: `2px solid ${BRACKET_COLOR}`,
                        borderBottom: `2px solid ${BRACKET_COLOR}`,
                      }} />
                      <div style={{
                        position: 'absolute', right: 0, top: 0, width: 8, height: BAR_H,
                        borderRight: `2px solid ${BRACKET_COLOR}`,
                        borderTop: `2px solid ${BRACKET_COLOR}`,
                        borderBottom: `2px solid ${BRACKET_COLOR}`,
                      }} />
                    </div>
                  );
                })()}
              </div>
            </div>
            {!isCollapsed && phases.flatMap(phase => {
              const phaseAssignments = ia.filter(a => a.phase === phase);
              if (phaseAssignments.length === 0) return [];
              const color = appearance.phase_colors[phase] ?? PHASE_COLORS[phase];

              // ОПЭ — 2 строки: Аналитик и Программист. Группируем по employee_role.
              // Для остальных фаз — одна строка (как раньше).
              const subgroups: Array<{
                key: string;
                roleLabel: string | null;
                assignments: AssignmentOut[];
              }> = [];
              if (phase === 'opo') {
                const analystA = phaseAssignments.filter(a =>
                  ANALYST_ROLE_CODES.has((a.employee_role ?? '').toLowerCase()),
                );
                const devA = phaseAssignments.filter(a =>
                  DEV_ROLE_CODES.has((a.employee_role ?? '').toLowerCase()),
                );
                const otherA = phaseAssignments.filter(
                  a => !analystA.includes(a) && !devA.includes(a),
                );
                if (analystA.length > 0) subgroups.push({ key: 'opo-an', roleLabel: 'Аналитик', assignments: analystA });
                if (devA.length > 0) subgroups.push({ key: 'opo-dev', roleLabel: 'Программист', assignments: devA });
                if (otherA.length > 0) subgroups.push({ key: 'opo-other', roleLabel: 'Иное', assignments: otherA });
                if (subgroups.length === 0) {
                  subgroups.push({ key: 'opo', roleLabel: null, assignments: phaseAssignments });
                }
              } else {
                subgroups.push({ key: phase, roleLabel: null, assignments: phaseAssignments });
              }

              return subgroups.map(sg => {
                const empName = sg.assignments[0].employee_name;
                const empRole = sg.assignments[0].employee_role;
                const empId = sg.assignments[0].employee_id;
                const sgHours = sg.assignments.reduce((s, a) => s + (a.hours_allocated ?? 0), 0);
                const title = sg.roleLabel
                  ? `${PHASE_LABELS[phase]} · ${sg.roleLabel}`
                  : PHASE_LABELS[phase];
                const isHighlighted = !!highlightedEmployeeId && empId === highlightedEmployeeId;
                const isDimmed = !!highlightedEmployeeId && !isHighlighted && phase !== 'qa';
                const assigneeNode = phase === 'qa' ? (
                  <span style={{ color: '#4a6a90' }}>—</span>
                ) : (
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onEmployeeRowClick && empId) {
                        onEmployeeRowClick(isHighlighted ? null : empId);
                      }
                    }}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      cursor: empId ? 'pointer' : 'default',
                      padding: '2px 4px',
                      borderRadius: 3,
                      background: isHighlighted ? 'rgba(0,201,200,0.18)' : 'transparent',
                    }}
                  >
                    <EmployeeAvatar name={empName} role={empRole} size={16} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{empName ?? '—'}</span>
                  </span>
                );
                return (
                  <div
                    key={sg.key}
                    data-gantt-row="true"
                    style={{
                      display: 'flex',
                      height: ROW_HEIGHT - 4,
                      borderBottom: '1px solid #0e2540',
                      background: isHighlighted ? 'rgba(0,201,200,0.18)' : 'transparent',
                    }}
                  >
                    <ItemTitleCell
                      title={title}
                      jiraKey={null}
                      leftColWidth={leftColWidth}
                      dotColor={color}
                      assignee={assigneeNode}
                      hours={sgHours > 0 ? `${Math.round(sgHours)} ч` : ''}
                    />
                    <div data-gantt-track="true" style={{ ...trackStyle(trackWidthPx) }}>
                      {sg.assignments.filter(a => a.start_date && a.end_date).map(a => {
                        // Канонический ключ для chain-стрелок (QA→opo и т.д.).
                        const refKey = `${a.backlog_item_id}-${a.phase}-${a.part_number}`;
                        // Доп. role-ключ для ресурс-стрелок analyst→opo-an, dev→opo-dev.
                        const extras: string[] = [];
                        if (a.phase === 'opo' && sg.key === 'opo-an') {
                          extras.push(`${a.backlog_item_id}-opo-an-${a.part_number}`);
                        } else if (a.phase === 'opo' && sg.key === 'opo-dev') {
                          extras.push(`${a.backlog_item_id}-opo-dev-${a.part_number}`);
                        }
                        return (
                          <PhaseBar
                            key={a.id}
                            assignment={a}
                            planId={planId}
                            timeline={timeline}
                            refKey={refKey}
                            extraRefKeys={extras}
                            rowRefs={rowRefs}
                            color={color}
                            showResize={a.phase !== 'qa'}
                            employees={employees}
                            hasConflict={conflictSet.has(a.id)}
                            dimmed={isDimmed}
                            onClick={onAssignmentClick ? () => onAssignmentClick(a.id) : undefined}
                            unavailableDays={
                              (a as AssignmentOut & {
                                unavailable_days?: Array<{
                                  date: string;
                                  type: 'weekend' | 'holiday' | 'absence' | 'block';
                                }>;
                              }).unavailable_days
                            }
                            highlightedEmployeeId={highlightedEmployeeId}
                            pulseEmp={rpPrefs.pulse_highlighted_employee}
                            pulseCp={rpPrefs.pulse_critical_path}
                          />
                        );
                      })}
                      {/* Task 21: dashed connectors between split parts */}
                      {(() => {
                        const dated = sg.assignments
                          .filter(a => a.start_date && a.end_date)
                          .sort((x, y) => (x.part_number ?? 1) - (y.part_number ?? 1));
                        if (dated.length < 2) return null;
                        return dated.slice(1).map((next, i) => {
                          const prev = dated[i];
                          if (!prev.end_date || !next.start_date) return null;
                          const leftPct = dateToLeft(prev.end_date, timeline);
                          const rightPct = dateToLeft(next.start_date, timeline);
                          const widthPct = rightPct - leftPct;
                          if (widthPct <= 0) return null;
                          return (
                            <div
                              key={`conn-${prev.id}-${next.id}`}
                              style={{
                                position: 'absolute',
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                top: 'calc(50% - 1px)',
                                height: 2,
                                borderTop: `1px dashed ${color}`,
                                zIndex: 1,
                                pointerEvents: 'none',
                                opacity: 0.6,
                              }}
                            />
                          );
                        });
                      })()}
                    </div>
                  </div>
                );
              });
            })}
          </div>
        );
      })}
    </>
  );
}

function ResourceTrackRows({ assignments, timeline, leftColWidth, trackWidthPx, rowRefs, onAssignmentClick }: SubProps) {
  const itemOrder = useMemo(
    () => [...new Set(assignments.map(a => a.backlog_item_id))],
    [assignments],
  );

  const byEmployee = useMemo(() => {
    const map = new Map<string, { name: string; assignments: AssignmentOut[] }>();
    for (const a of assignments) {
      const empId = a.employee_id ?? '__unassigned__';
      if (!map.has(empId)) {
        map.set(empId, { name: a.employee_name ?? 'Без исполнителя', assignments: [] });
      }
      map.get(empId)!.assignments.push(a);
    }
    return [...map.entries()];
  }, [assignments]);

  return (
    <>
      {byEmployee.map(([empId, { name, assignments: empAssignments }]) => (
        <div
          key={empId}
          style={{
            display: 'flex',
            height: ROW_HEIGHT + 4,
            borderBottom: '1px solid #1e3a5f',
            background: ROW_BG,
          }}
        >
          <div style={{
            width: leftColWidth,
            flexShrink: 0,
            borderRight: '1px solid #1e3a5f',
            padding: '0 12px',
            display: 'flex',
            alignItems: 'center',
            fontSize: 13,
            fontWeight: 600,
            color: '#fff',
            overflow: 'hidden',
            whiteSpace: 'nowrap',
            textOverflow: 'ellipsis',
            gap: 8,
            position: 'sticky',
            left: 0,
            zIndex: STICKY_CELL_Z,
            background: '#0a1628',
            boxShadow: '0 1px 0 0 #1e3a5f',
          }}>
            <EmployeeAvatar name={empAssignments[0]?.employee_name ?? null} role={empAssignments[0]?.employee_role} size={20} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
          </div>
          <div style={trackStyle(trackWidthPx)}>
            {empAssignments.filter(a => a.start_date && a.end_date).map(a => {
              const idx2 = itemOrder.indexOf(a.backlog_item_id);
              const color = getItemColor(idx2);
              const left = dateToLeft(a.start_date!, timeline);
              const width = datesToWidth(a.start_date!, a.end_date!, timeline);
              const refKey = `${a.backlog_item_id}-${a.phase}-${a.part_number}`;
              return (
                <div
                  key={a.id}
                  ref={el => {
                    if (el) rowRefs.current.set(refKey, el);
                    else rowRefs.current.delete(refKey);
                  }}
                  title={`${a.backlog_item_title} — ${PHASE_LABELS[a.phase]} (${a.hours_allocated?.toFixed(0)}ч)`}
                  onClick={(e) => {
                    if (a.phase === 'qa') return;
                    e.stopPropagation();
                    onAssignmentClick?.(a.id);
                  }}
                  style={{
                    position: 'absolute',
                    left: `${left}%`,
                    width: `${Math.max(width, 0.8)}%`,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    height: 22,
                    background: color,
                    opacity: 0.85,
                    borderRadius: 3,
                    zIndex: 2,
                    display: 'flex',
                    alignItems: 'center',
                    paddingLeft: 4,
                    fontSize: 9,
                    color: '#fff',
                    fontWeight: 700,
                    overflow: 'hidden',
                    whiteSpace: 'nowrap',
                    cursor: a.phase === 'qa' ? 'default' : 'pointer',
                    outline: a.is_pinned ? '1px solid #00c9c8' : 'none',
                  }}
                >
                  {a.backlog_item_title}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </>
  );
}

export default function GanttRows(props: Props) {
  if (props.viewMode === 'portfolio') return <PortfolioRows {...props} />;
  if (props.viewMode === 'resource-track') return <ResourceTrackRows {...props} />;
  return <TwoLevelRows {...props} />;
}
