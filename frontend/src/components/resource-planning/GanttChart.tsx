import { useRef, useMemo, useState } from 'react';
import type { AssignmentOut, DependencyOut, ScheduledBlock } from '../../api/resourcePlanning';
import type { EmployeeResponse } from '../../types/api';
import type { TimelineScale } from '../../utils/gantt';
import { buildTimeline, buildWorkdayTimeline, dateToLeft, quarterBounds, PX_PER_DAY } from '../../utils/gantt';
import type { ViewMode } from './GanttRows';
import TimelineHeader from './TimelineHeader';
import GanttRows from './GanttRows';
import BlockedZones from './BlockedZones';
import NonWorkingZones from './NonWorkingZones';
import TrackGridlines from './TrackGridlines';
import DependencyArrows from './DependencyArrows';
import { useProductionCalendarYear } from '../../hooks/useProductionCalendar';
import { useRpPreferences } from '../../hooks/useRpPreferences';

const LEFT_COL_DEFAULT = 280;
const LEFT_COL_TWO_LEVEL = 540;

interface Props {
  assignments: AssignmentOut[];
  blocks: ScheduledBlock[];
  quarter: string;
  year: number;
  viewMode: ViewMode;
  showRelayArrows?: boolean;
  planId: string;
  employees: EmployeeResponse[];
  scale?: TimelineScale;
  dependencies?: DependencyOut[];
  depDrawMode?: boolean;
  onCreateDependency?: (fromItemId: string, toItemId: string) => void;
  onDeleteDependency?: (depId: string) => void;
  collapsedItemIds?: string[];
  onToggleCollapse?: (itemId: string, collapsed: boolean) => void;
  conflictAssignmentIds?: string[];
  onAssignmentClick?: (assignmentId: string) => void;
  hideWeekends?: boolean;
  highlightedEmployeeId?: string | null;
  onEmployeeRowClick?: (employeeId: string | null) => void;
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
  scale = 'week',
  dependencies = [],
  depDrawMode = false,
  onCreateDependency,
  onDeleteDependency,
  collapsedItemIds,
  onToggleCollapse,
  conflictAssignmentIds,
  onAssignmentClick,
  hideWeekends = false,
  highlightedEmployeeId,
  onEmployeeRowClick,
}: Props) {
  const LEFT_COL = viewMode === 'two-level' ? LEFT_COL_TWO_LEVEL : LEFT_COL_DEFAULT;
  const [pendingFromItem, setPendingFromItem] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<string, HTMLElement>>(new Map());

  const calendarQuery = useProductionCalendarYear(year);
  const calendar = calendarQuery.data ?? [];
  const { prefs } = useRpPreferences();

  // Workday mode forces day scale (week/month labels don't align with workday blocks)
  const effectiveScale: TimelineScale = hideWeekends ? 'day' : scale;

  const hasOoQ = useMemo(() => assignments.some(a => a.out_of_quarter), [assignments]);
  const oogMonths = hasOoQ ? (prefs.out_of_quarter_months ?? 1) : 0;

  const qEndIso = useMemo(() => {
    const { end } = quarterBounds(quarter, year);
    return end.toISOString().slice(0, 10);
  }, [quarter, year]);

  const timeline = useMemo(() => {
    const { start, end } = quarterBounds(quarter, year);
    const extEnd = new Date(end);
    if (oogMonths > 0) extEnd.setMonth(extEnd.getMonth() + oogMonths);
    if (hideWeekends) return buildWorkdayTimeline(start, extEnd, calendar);
    return buildTimeline(start, extEnd);
  }, [quarter, year, hideWeekends, calendar, oogMonths]);

  const pxPerDay = PX_PER_DAY[effectiveScale];
  const trackWidthPx = Math.round(timeline.totalDays * pxPerDay);

  const todayLeft = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return dateToLeft(today, timeline);
  }, [timeline]);

  const handleItemClick = (itemId: string) => {
    if (!depDrawMode || !onCreateDependency) return;
    if (!pendingFromItem) {
      setPendingFromItem(itemId);
    } else if (pendingFromItem !== itemId) {
      onCreateDependency(pendingFromItem, itemId);
      setPendingFromItem(null);
    } else {
      setPendingFromItem(null);
    }
  };

  return (
    <div
      style={{
        background: '#0a1628',
        border: '1px solid #1e3a5f',
        borderRadius: 8,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {depDrawMode && (
        <div style={{
          padding: '6px 12px',
          background: 'rgba(255,122,69,0.12)',
          borderBottom: '1px solid rgba(255,122,69,0.4)',
          color: '#ff7a45',
          fontSize: 12,
        }}>
          {pendingFromItem
            ? 'Кликните по второй инициативе, чтобы создать связь (Ctrl+Click — сбросить выбор)'
            : 'Режим связей: кликните по инициативе-источнику'}
        </div>
      )}

      <div
        ref={containerRef}
        style={{
          position: 'relative',
          overflowX: 'auto',
          overflowY: 'visible',
        }}
      >
        <div
          ref={innerRef}
          className="rp-track-animated"
          style={{
            position: 'relative',
            width: LEFT_COL + trackWidthPx,
            minWidth: '100%',
          }}
        >
          <div style={{ position: 'sticky', top: 'var(--rp-page-sticky-h, 0px)', zIndex: 30, background: '#0a1628' }}>
            <TimelineHeader
              timeline={timeline}
              leftColWidth={LEFT_COL}
              scale={effectiveScale}
              trackWidthPx={trackWidthPx}
              calendar={calendar}
            />
          </div>

          {/* Non-working zones (weekends/holidays) — background layer */}
          <div style={{
            position: 'absolute',
            left: LEFT_COL,
            width: trackWidthPx,
            top: 0, bottom: 0,
            pointerEvents: 'none',
            zIndex: 0,
          }}>
            <NonWorkingZones
              timeline={timeline}
              calendar={calendar}
              scale={effectiveScale}
              hideInWeekMonth
            />
          </div>

          {/* Vertical gridlines */}
          <div style={{
            position: 'absolute',
            left: LEFT_COL,
            width: trackWidthPx,
            top: 0, bottom: 0,
            pointerEvents: 'none',
            zIndex: 1,
          }}>
            <TrackGridlines timeline={timeline} scale={effectiveScale} />
          </div>

          {/* Today marker */}
          <div style={{
            position: 'absolute',
            left: LEFT_COL + (todayLeft / 100) * trackWidthPx,
            top: 0, bottom: 0,
            width: 2,
            background: 'rgba(0,201,200,0.6)',
            zIndex: 20,
            pointerEvents: 'none',
          }} />

          {/* Quarter-end divider (shows when timeline is extended for out_of_quarter assignments) */}
          {hasOoQ && (
            <div style={{
              position: 'absolute',
              left: LEFT_COL + (dateToLeft(qEndIso, timeline) / 100) * trackWidthPx,
              top: 0,
              bottom: 0,
              width: 0,
              borderRight: '2px dashed #ffb432',
              zIndex: 19,
              pointerEvents: 'none',
            }} />
          )}

          {/* Blocked zones */}
          <div style={{
            position: 'absolute',
            left: LEFT_COL,
            width: trackWidthPx,
            top: 0, bottom: 0,
            pointerEvents: 'none',
          }}>
            <BlockedZones blocks={blocks} timeline={timeline} />
          </div>

          {/* SVG arrows */}
          <DependencyArrows
            assignments={assignments}
            rowRefs={rowRefs}
            containerRef={innerRef as React.RefObject<HTMLDivElement>}
            showRelayArrows={showRelayArrows}
            manualDependencies={dependencies}
            onDeleteDependency={onDeleteDependency}
            highlightedEmployeeId={highlightedEmployeeId}
            redrawKey={`${effectiveScale}:${trackWidthPx}`}
          />

          <GanttRows
            assignments={assignments}
            timeline={timeline}
            viewMode={viewMode}
            leftColWidth={LEFT_COL}
            trackWidthPx={trackWidthPx}
            rowRefs={rowRefs}
            planId={planId}
            employees={employees}
            depDrawMode={depDrawMode}
            pendingFromItem={pendingFromItem}
            onItemClick={handleItemClick}
            collapsedItemIds={collapsedItemIds}
            onToggleCollapse={onToggleCollapse}
            conflictAssignmentIds={conflictAssignmentIds}
            onAssignmentClick={onAssignmentClick}
            highlightedEmployeeId={highlightedEmployeeId}
            onEmployeeRowClick={onEmployeeRowClick}
            quarterEndDate={qEndIso}
          />
        </div>
      </div>
    </div>
  );
}
