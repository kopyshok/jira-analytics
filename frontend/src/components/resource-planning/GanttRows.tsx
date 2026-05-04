import { useMemo } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';
import type { EmployeeResponse } from '../../types/api';
import type { GanttTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth, PHASE_COLORS, PHASE_LABELS, getItemColor } from '../../utils/gantt';
import EmployeeAvatar from './EmployeeAvatar';
import AssignEmployeePopover from './AssignEmployeePopover';

export type ViewMode = 'portfolio' | 'two-level' | 'resource-track';

interface Props {
  assignments: AssignmentOut[];
  timeline: GanttTimeline;
  viewMode: ViewMode;
  leftColWidth: number;
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  planId: string;
  employees: EmployeeResponse[];
}

type SubProps = Omit<Props, 'viewMode'>;

const ROW_HEIGHT = 36;
const JIRA_BASE = 'https://itgri.atlassian.net';

function ItemTitleCell({
  title, jiraKey, leftColWidth, fontWeight = 600,
}: { title: string; jiraKey: string | null; leftColWidth: number; fontWeight?: number }) {
  return (
    <div style={{
      width: leftColWidth,
      flexShrink: 0,
      borderRight: '1px solid #1e3a5f',
      padding: '6px 12px',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      gap: 2,
      fontSize: 13,
      fontWeight,
      color: '#fff',
      overflow: 'hidden',
    }}>
      {jiraKey && (
        <a
          href={`${JIRA_BASE}/browse/${jiraKey}`}
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: 10, color: '#7a9ab8', textDecoration: 'none', letterSpacing: 0.3 }}
        >
          {jiraKey}
        </a>
      )}
      <div style={{
        fontSize: 13, lineHeight: 1.3, whiteSpace: 'normal', wordBreak: 'break-word',
      }}>
        {title}
      </div>
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
            background: idx % 2 === 0 ? 'rgba(0,201,200,0.03)' : 'transparent',
          }}
        >
          <ItemTitleCell title={title} jiraKey={key} leftColWidth={leftColWidth} />
          <div style={{ flex: 1, position: 'relative' }}>
            {itemAssignments.filter(a => a.start_date && a.end_date).map(a => {
              const left = dateToLeft(a.start_date!, timeline);
              const width = datesToWidth(a.start_date!, a.end_date!, timeline);
              const color = PHASE_COLORS[a.phase] ?? '#888';
              const bar = (
                <div
                  title={`${PHASE_LABELS[a.phase]} — ${a.employee_name ?? '—'} (${a.hours_allocated?.toFixed(0)}ч)`}
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

function TwoLevelRows({ assignments, timeline, leftColWidth, rowRefs, planId, employees }: SubProps) {
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
      {byItem.map(([itemId, { title, key, assignments: ia }]) => {
        const phases = ['analyst', 'dev', 'qa', 'opo'] as const;
        return (
          <div key={itemId}>
            <div
              ref={el => {
                if (el) rowRefs.current.set(itemId, el);
                else rowRefs.current.delete(itemId);
              }}
              style={{
                display: 'flex',
                minHeight: ROW_HEIGHT,
                borderBottom: '1px solid #1e3a5f',
                background: 'rgba(0,201,200,0.05)',
              }}
            >
              <ItemTitleCell title={title} jiraKey={key} leftColWidth={leftColWidth} fontWeight={700} />
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
              return (
                <div
                  key={phase}
                  style={{
                    display: 'flex',
                    height: ROW_HEIGHT - 4,
                    borderBottom: '1px solid #0e2540',
                  }}
                >
                  <div style={{
                    width: leftColWidth,
                    flexShrink: 0,
                    borderRight: '1px solid #1e3a5f',
                    padding: '0 12px 0 32px',
                    display: 'flex',
                    alignItems: 'center',
                    fontSize: 12,
                    color: '#8ab0d8',
                    gap: 6,
                  }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }} />
                    {PHASE_LABELS[phase]}
                    <span style={{ marginLeft: 'auto', paddingRight: 4 }}>
                      {phase === 'qa' ? (
                        <span style={{ fontSize: 10, color: '#4a6a90' }}>—</span>
                      ) : (
                        <EmployeeAvatar name={empName} role={empRole} size={18} />
                      )}
                    </span>
                  </div>
                  <div style={{ flex: 1, position: 'relative' }}>
                    {phaseAssignments.filter(a => a.start_date && a.end_date).map(a => {
                      const left = dateToLeft(a.start_date!, timeline);
                      const width = datesToWidth(a.start_date!, a.end_date!, timeline);
                      const refKey = `${a.backlog_item_id}-${a.phase}-${a.part_number}`;
                      const bar = (
                        <div
                          ref={el => {
                            if (el) rowRefs.current.set(refKey, el);
                            else rowRefs.current.delete(refKey);
                          }}
                          title={`${PHASE_LABELS[a.phase]}, ч. ${a.part_number} — ${a.hours_allocated?.toFixed(0)}ч`}
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
                            cursor: a.phase === 'qa' ? 'default' : 'pointer',
                          }}
                        />
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
      {byEmployee.map(([empId, { name, assignments: empAssignments }]) => (
        <div
          key={empId}
          style={{
            display: 'flex',
            height: ROW_HEIGHT + 4,
            borderBottom: '1px solid #1e3a5f',
            background: 'rgba(0,201,200,0.03)',
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
              const idx = itemOrder.indexOf(a.backlog_item_id);
              const color = getItemColor(idx);
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
