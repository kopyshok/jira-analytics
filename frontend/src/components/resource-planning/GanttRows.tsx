import { useEffect, useMemo, useState } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';
import type { EmployeeResponse } from '../../types/api';
import type { GanttTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth, PHASE_COLORS, PHASE_LABELS, getItemColor } from '../../utils/gantt';
import EmployeeAvatar from './EmployeeAvatar';
import AssignEmployeePopover from './AssignEmployeePopover';
import { usePatchAssignment } from '../../hooks/useResourcePlanning';

export type ViewMode = 'portfolio' | 'two-level' | 'resource-track';

interface Props {
  assignments: AssignmentOut[];
  timeline: GanttTimeline;
  viewMode: ViewMode;
  leftColWidth: number;
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  planId: string;
  employees: EmployeeResponse[];
  depDrawMode?: boolean;
  pendingFromItem?: string | null;
  onItemClick?: (itemId: string) => void;
}

type SubProps = Omit<Props, 'viewMode'>;

const ROW_HEIGHT = 36;
const JIRA_BASE = 'https://itgri.atlassian.net';
const ZEBRA_BG_EVEN = 'rgba(0,201,200,0.04)';
const ZEBRA_BG_ODD = 'rgba(0,0,0,0.18)';

function ItemTitleCell({
  title, jiraKey, leftColWidth, fontWeight = 600, role, assignee, hours,
}: {
  title: string; jiraKey: string | null; leftColWidth: number; fontWeight?: number;
  role?: React.ReactNode; assignee?: React.ReactNode; hours?: React.ReactNode;
}) {
  return (
    <div style={{
      width: leftColWidth,
      flexShrink: 0,
      borderRight: '1px solid #1e3a5f',
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 1fr) 96px 140px 60px',
      columnGap: 8,
      alignItems: 'center',
      padding: '6px 12px',
      fontSize: 13,
      fontWeight,
      color: '#fff',
      overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, overflow: 'hidden' }}>
        {jiraKey && (
          <a
            href={`${JIRA_BASE}/browse/${jiraKey}`}
            target="_blank"
            rel="noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ fontSize: 10, color: '#7a9ab8', textDecoration: 'none', letterSpacing: 0.3 }}
          >
            {jiraKey}
          </a>
        )}
        <div style={{ fontSize: 13, lineHeight: 1.3, whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
          {title}
        </div>
      </div>
      <div style={{ fontSize: 11, color: '#8ab0d8' }}>{role ?? ''}</div>
      <div style={{ fontSize: 11, color: '#8ab0d8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {assignee ?? ''}
      </div>
      <div style={{ fontSize: 11, color: '#8ab0d8', textAlign: 'right' }}>{hours ?? ''}</div>
    </div>
  );
}

function PortfolioRows({ assignments, timeline, leftColWidth, rowRefs, planId, employees }: SubProps) {
  const byItem = useMemo(() => {
    const map = new Map<string, { title: string; key: string | null; assignments: AssignmentOut[] }>();
    for (const a of assignments) {
      if (!map.has(a.backlog_item_id)) {
        map.set(a.backlog_item_id, {
          title: a.backlog_item_title,
          key: a.backlog_item_key,
          assignments: [],
        });
      }
      map.get(a.backlog_item_id)!.assignments.push(a);
    }
    return [...map.entries()];
  }, [assignments]);

  return (
    <>
      {byItem.map(([itemId, { title, key, assignments: itemAssignments }], idx) => (
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
            background: idx % 2 === 0 ? ZEBRA_BG_EVEN : ZEBRA_BG_ODD,
          }}
        >
          <ItemTitleCell title={title} jiraKey={key} leftColWidth={leftColWidth} />
          <div style={{ flex: 1, position: 'relative' }}>
            {itemAssignments.filter(a => a.start_date && a.end_date).map(a => {
              const left = dateToLeft(a.start_date!, timeline);
              const width = datesToWidth(a.start_date!, a.end_date!, timeline);
              const color = PHASE_COLORS[a.phase] ?? '#888';
              const isChunked = a.chunks_total != null && a.chunks_total > 1;
              const bar = (
                <div
                  title={`${PHASE_LABELS[a.phase]}${isChunked ? ` (${(a.chunk_index ?? 0) + 1}/${a.chunks_total})` : ''} — ${a.employee_name ?? '—'} (${a.hours_allocated?.toFixed(0)}ч)`}
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
                  {isChunked && (
                    <span style={{
                      fontSize: 8,
                      background: 'rgba(0,0,0,0.25)',
                      borderRadius: 2,
                      padding: '0 2px',
                      flexShrink: 0,
                    }}>
                      {(a.chunk_index ?? 0) + 1}/{a.chunks_total}
                    </span>
                  )}
                </div>
              );
              return (
                <AssignEmployeePopover
                  key={a.id}
                  assignmentId={a.id}
                  planId={planId}
                  phase={a.phase}
                  currentEmployeeId={a.employee_id}
                  employees={employees}
                  isPinned={a.is_pinned}
                >
                  {bar}
                </AssignEmployeePopover>
              );
            })}
          </div>
        </div>
      ))}
    </>
  );
}

interface PhaseBarDragProps {
  assignment: AssignmentOut;
  planId: string;
  timeline: GanttTimeline;
  children: React.ReactNode;
  refKey: string;
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  color: string;
  showResize: boolean;
}

function PhaseBarDraggable({ assignment, planId, timeline, children, refKey, rowRefs, color, showResize }: PhaseBarDragProps) {
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

  const onMouseMove = (e: MouseEvent) => {
    if (!drag) return;
    const dxPx = e.clientX - drag.startClientX;
    const pxPerDay = drag.rowWidthPx / timeline.totalDays;
    const dxDays = Math.round(dxPx / pxPerDay);
    if (dxDays === 0) return;
    const sd = new Date(drag.origStart + 'T00:00:00');
    const ed = new Date(drag.origEnd + 'T00:00:00');
    if (drag.mode === 'move') {
      sd.setDate(sd.getDate() + dxDays);
      ed.setDate(ed.getDate() + dxDays);
    } else if (drag.mode === 'resize-start') {
      sd.setDate(sd.getDate() + dxDays);
      if (sd >= ed) sd.setTime(ed.getTime() - 86_400_000);
    } else {
      ed.setDate(ed.getDate() + dxDays);
      if (ed <= sd) ed.setTime(sd.getTime() + 86_400_000);
    }
    const newStart = sd.toISOString().slice(0, 10);
    const newEnd = ed.toISOString().slice(0, 10);
    setPreviewLeft(dateToLeft(newStart, timeline));
    setPreviewWidth(datesToWidth(newStart, newEnd, timeline));
  };

  const onMouseUp = (e: MouseEvent) => {
    if (!drag) return;
    const dxPx = e.clientX - drag.startClientX;
    const pxPerDay = drag.rowWidthPx / timeline.totalDays;
    const dxDays = Math.round(dxPx / pxPerDay);
    if (dxDays !== 0) {
      const sd = new Date(drag.origStart + 'T00:00:00');
      const ed = new Date(drag.origEnd + 'T00:00:00');
      if (drag.mode === 'move') {
        sd.setDate(sd.getDate() + dxDays);
        ed.setDate(ed.getDate() + dxDays);
      } else if (drag.mode === 'resize-start') {
        sd.setDate(sd.getDate() + dxDays);
        if (sd >= ed) sd.setTime(ed.getTime() - 86_400_000);
      } else {
        ed.setDate(ed.getDate() + dxDays);
        if (ed <= sd) ed.setTime(sd.getTime() + 86_400_000);
      }
      const newStart = sd.toISOString().slice(0, 10);
      const newEnd = ed.toISOString().slice(0, 10);
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

  // attach window listeners while dragging
  useMemoizedDragListeners(drag, onMouseMove, onMouseUp);

  return (
    <div
      ref={el => {
        if (el) rowRefs.current.set(refKey, el);
        else rowRefs.current.delete(refKey);
      }}
      onMouseDown={(e) => beginDrag(e, 'move')}
      style={{ position: 'absolute', left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    >
      <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'auto' }}>
        {children}
      </div>
      {showResize && assignment.start_date && assignment.end_date && (
        <>
          <div
            onMouseDown={(e) => beginDrag(e, 'resize-start')}
            style={{
              position: 'absolute',
              top: '50%',
              transform: 'translateY(-50%)',
              left: `calc(${dateToLeft(assignment.start_date, timeline)}% - 3px)`,
              width: 6,
              height: 22,
              cursor: 'ew-resize',
              background: 'rgba(255,255,255,0.0)',
              zIndex: 4,
              pointerEvents: 'auto',
            }}
          />
          <div
            onMouseDown={(e) => beginDrag(e, 'resize-end')}
            style={{
              position: 'absolute',
              top: '50%',
              transform: 'translateY(-50%)',
              left: `calc(${dateToLeft(assignment.start_date, timeline) + datesToWidth(assignment.start_date, assignment.end_date, timeline)}% - 3px)`,
              width: 6,
              height: 22,
              cursor: 'ew-resize',
              background: 'rgba(255,255,255,0.0)',
              zIndex: 4,
              pointerEvents: 'auto',
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

function TwoLevelRows({
  assignments, timeline, leftColWidth, rowRefs, planId, employees,
  depDrawMode, pendingFromItem, onItemClick,
}: SubProps) {
  const byItem = useMemo(() => {
    const map = new Map<string, { title: string; key: string | null; assignments: AssignmentOut[] }>();
    for (const a of assignments) {
      if (!map.has(a.backlog_item_id)) {
        map.set(a.backlog_item_id, {
          title: a.backlog_item_title,
          key: a.backlog_item_key,
          assignments: [],
        });
      }
      map.get(a.backlog_item_id)!.assignments.push(a);
    }
    return [...map.entries()];
  }, [assignments]);

  return (
    <>
      {byItem.map(([itemId, { title, key, assignments: ia }], itemIdx) => {
        const phases = ['analyst', 'dev', 'qa', 'opo'] as const;
        const itemBg = itemIdx % 2 === 0 ? ZEBRA_BG_EVEN : ZEBRA_BG_ODD;
        const isPendingFrom = pendingFromItem === itemId;

        const totalHours = ia.reduce((s, a) => s + (a.hours_allocated ?? 0), 0);
        const assigneeNames = Array.from(new Set(ia.map(a => a.employee_name).filter(Boolean))).join(', ');

        return (
          <div key={itemId} style={{ background: itemBg }}>
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
                background: isPendingFrom ? 'rgba(255,122,69,0.18)' : 'rgba(0,201,200,0.05)',
                cursor: depDrawMode ? 'crosshair' : 'default',
                outline: isPendingFrom ? '2px solid #ff7a45' : 'none',
              }}
            >
              <ItemTitleCell
                title={title}
                jiraKey={key}
                leftColWidth={leftColWidth}
                fontWeight={700}
                assignee={assigneeNames || '—'}
                hours={totalHours > 0 ? `${Math.round(totalHours)} ч` : ''}
              />
              <div style={{ flex: 1, position: 'relative' }}>
                {(() => {
                  const starts = ia.filter(a => a.start_date).map(a => a.start_date!).sort();
                  const ends = ia.filter(a => a.end_date).map(a => a.end_date!).sort();
                  if (!starts[0] || !ends.at(-1)) return null;
                  const left = dateToLeft(starts[0], timeline);
                  const width = datesToWidth(starts[0], ends.at(-1)!, timeline);
                  return (
                    <div style={{
                      position: 'absolute',
                      left: `${left}%`,
                      width: `${width}%`,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      height: 24,
                      background: 'rgba(0,201,200,0.15)',
                      border: '1px solid rgba(0,201,200,0.4)',
                      borderRadius: 4,
                      zIndex: 2,
                    }} />
                  );
                })()}
              </div>
            </div>
            {phases.map(phase => {
              const phaseAssignments = ia.filter(a => a.phase === phase);
              if (phaseAssignments.length === 0) return null;
              const color = PHASE_COLORS[phase];
              const empName = phaseAssignments[0].employee_name;
              const empRole = phaseAssignments[0].employee_role;
              const phaseHours = phaseAssignments.reduce((s, a) => s + (a.hours_allocated ?? 0), 0);
              return (
                <div
                  key={phase}
                  data-gantt-row="true"
                  style={{
                    display: 'flex',
                    height: ROW_HEIGHT - 4,
                    borderBottom: '1px solid #0e2540',
                  }}
                >
                  <ItemTitleCell
                    title=""
                    jiraKey={null}
                    leftColWidth={leftColWidth}
                    role={
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }} />
                        {PHASE_LABELS[phase]}
                      </span>
                    }
                    assignee={
                      phase === 'qa' ? <span style={{ color: '#4a6a90' }}>—</span> : (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                          <EmployeeAvatar name={empName} role={empRole} size={16} />
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{empName ?? '—'}</span>
                        </span>
                      )
                    }
                    hours={phaseHours > 0 ? `${Math.round(phaseHours)} ч` : ''}
                  />
                  <div data-gantt-track="true" style={{ flex: 1, position: 'relative' }}>
                    {phaseAssignments.filter(a => a.start_date && a.end_date).map(a => {
                      const left = dateToLeft(a.start_date!, timeline);
                      const width = datesToWidth(a.start_date!, a.end_date!, timeline);
                      const refKey = `${a.backlog_item_id}-${a.phase}-${a.part_number}`;
                      const isChunkedRow = a.chunks_total != null && a.chunks_total > 1;
                      const bar = (
                        <div
                          title={`${PHASE_LABELS[a.phase]}${isChunkedRow ? ` (${(a.chunk_index ?? 0) + 1}/${a.chunks_total})` : `, ч. ${a.part_number}`} — ${a.hours_allocated?.toFixed(0)}ч`}
                          style={{
                            position: 'absolute',
                            left: `${left}%`,
                            width: `${Math.max(width, 0.8)}%`,
                            top: '50%',
                            transform: 'translateY(-50%)',
                            height: 18,
                            background: color,
                            opacity: a.is_on_critical_path ? 1 : 0.75,
                            borderRadius: 3,
                            border: a.is_on_critical_path ? '1px solid #e85d4a' : 'none',
                            boxShadow: a.is_on_critical_path ? '0 0 6px rgba(232,93,74,0.5)' : 'none',
                            outline: a.is_pinned ? '1px solid #00c9c8' : 'none',
                            zIndex: 2,
                            cursor: a.phase === 'qa' ? 'default' : 'grab',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          {isChunkedRow && (
                            <span style={{
                              fontSize: 8,
                              color: '#0d1c33',
                              fontWeight: 700,
                              background: 'rgba(0,0,0,0.2)',
                              borderRadius: 2,
                              padding: '0 2px',
                              pointerEvents: 'none',
                            }}>
                              {(a.chunk_index ?? 0) + 1}/{a.chunks_total}
                            </span>
                          )}
                        </div>
                      );
                      return (
                        <PhaseBarDraggable
                          key={a.id}
                          assignment={a}
                          planId={planId}
                          timeline={timeline}
                          refKey={refKey}
                          rowRefs={rowRefs}
                          color={color}
                          showResize={a.phase !== 'qa'}
                        >
                          <AssignEmployeePopover
                            assignmentId={a.id}
                            planId={planId}
                            phase={a.phase}
                            currentEmployeeId={a.employee_id}
                            employees={employees}
                            isPinned={a.is_pinned}
                          >
                            {bar}
                          </AssignEmployeePopover>
                        </PhaseBarDraggable>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}

function ResourceTrackRows({ assignments, timeline, leftColWidth, rowRefs, planId, employees }: SubProps) {
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
      {byEmployee.map(([empId, { name, assignments: empAssignments }], idx) => (
        <div
          key={empId}
          style={{
            display: 'flex',
            height: ROW_HEIGHT + 4,
            borderBottom: '1px solid #1e3a5f',
            background: idx % 2 === 0 ? ZEBRA_BG_EVEN : ZEBRA_BG_ODD,
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
          }}>
            <EmployeeAvatar name={empAssignments[0]?.employee_name ?? null} role={empAssignments[0]?.employee_role} size={20} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
          </div>
          <div style={{ flex: 1, position: 'relative' }}>
            {empAssignments.filter(a => a.start_date && a.end_date).map(a => {
              const idx2 = itemOrder.indexOf(a.backlog_item_id);
              const color = getItemColor(idx2);
              const left = dateToLeft(a.start_date!, timeline);
              const width = datesToWidth(a.start_date!, a.end_date!, timeline);
              const refKey = `${a.backlog_item_id}-${a.phase}-${a.part_number}`;
              const bar = (
                <div
                  ref={el => {
                    if (el) rowRefs.current.set(refKey, el);
                    else rowRefs.current.delete(refKey);
                  }}
                  title={`${a.backlog_item_title} — ${PHASE_LABELS[a.phase]} (${a.hours_allocated?.toFixed(0)}ч)`}
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
              return (
                <AssignEmployeePopover
                  key={a.id}
                  assignmentId={a.id}
                  planId={planId}
                  phase={a.phase}
                  currentEmployeeId={a.employee_id}
                  employees={employees}
                  isPinned={a.is_pinned}
                >
                  {bar}
                </AssignEmployeePopover>
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
