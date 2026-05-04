import { useRef, useMemo } from 'react';
import type { AssignmentOut, ScheduledBlock } from '../../api/resourcePlanning';
import type { EmployeeResponse } from '../../types/api';
import { buildTimeline, dateToLeft, quarterBounds } from '../../utils/gantt';
import type { ViewMode } from './GanttRows';
import TimelineHeader from './TimelineHeader';
import GanttRows from './GanttRows';
import BlockedZones from './BlockedZones';
import DependencyArrows from './DependencyArrows';

const LEFT_COL = 280;

interface Props {
  assignments: AssignmentOut[];
  blocks: ScheduledBlock[];
  quarter: string;
  year: number;
  viewMode: ViewMode;
  showRelayArrows?: boolean;
  planId: string;
  employees: EmployeeResponse[];
}

export default function GanttChart({
  assignments,
  blocks,
  quarter,
  year,
  viewMode,
  showRelayArrows = true,
  planId,
  employees,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<string, HTMLElement>>(new Map());

  const timeline = useMemo(() => {
    const { start, end } = quarterBounds(quarter, year);
    return buildTimeline(start, end);
  }, [quarter, year]);

  const todayLeft = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return dateToLeft(today, timeline);
  }, [timeline]);

  return (
    <div
      style={{
        background: '#0f2340',
        border: '1px solid #1e3a5f',
        borderRadius: 8,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <TimelineHeader timeline={timeline} leftColWidth={LEFT_COL} />

      <div
        ref={containerRef}
        style={{ position: 'relative', overflowY: 'auto', maxHeight: 'calc(100vh - 280px)' }}
      >
        {/* Today marker */}
        <div style={{
          position: 'absolute',
          left: `calc(${LEFT_COL}px + ${todayLeft / 100} * (100% - ${LEFT_COL}px))`,
          top: 0, bottom: 0,
          width: 2,
          background: 'rgba(0,201,200,0.6)',
          zIndex: 20,
          pointerEvents: 'none',
        }} />

        {/* Blocked zones */}
        <div style={{ position: 'absolute', left: LEFT_COL, right: 0, top: 0, bottom: 0, pointerEvents: 'none' }}>
          <BlockedZones blocks={blocks} timeline={timeline} />
        </div>

        {/* SVG arrows */}
        <DependencyArrows
          assignments={assignments}
          rowRefs={rowRefs}
          containerRef={containerRef as React.RefObject<HTMLDivElement>}
          showRelayArrows={showRelayArrows}
        />

        <GanttRows
          assignments={assignments}
          timeline={timeline}
          viewMode={viewMode}
          leftColWidth={LEFT_COL}
          rowRefs={rowRefs}
          planId={planId}
          employees={employees}
        />
      </div>
    </div>
  );
}
