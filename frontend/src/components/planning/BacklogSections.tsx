import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import BacklogAllocRow from './BacklogAllocRow';
import SubgroupSectionHeader from './SubgroupSectionHeader';
import { DARK_THEME } from '../../utils/constants';
import type { PlanningPageState } from '../../pages/PlanningPage';

/**
 * Строки бэклога сценария секциями групп с перетаскиванием — общие для
 * раскладки Aurora и раскладок обложек.
 */
export default function BacklogSections({ p }: { p: PlanningPageState }) {
  const {
    scenarioId,
    compact,
    flashingIds,
    roles,
    jiraBaseUrl,
    scenario,
    opoOff,
    allocations,
    allocLoading,
    continuation,
    personSort,
    handleDragEnd,
    resourceSummary,
    teamAssigneeOptions,
    isDraft,
    rowStateClass,
    toggleAllocation,
    registerRowRef,
    handlePriorityChange,
    handleAssigneeChange,
    handleDeveloperChange,
    hasSubgroups,
    subgroupOptions,
    shownSections,
    collapsedSections,
    toggleSection,
    handleSubgroupChange,
    handleOpenBreakdown,
    gridTemplate,
    gridGap,
  } = p;
  return (
  <DndContext
    collisionDetection={closestCenter}
    modifiers={[restrictToVerticalAxis]}
    onDragEnd={handleDragEnd}
  >
    <div>
    {shownSections.map((section) => {
      const collapsed = section.id !== null && collapsedSections.has(section.id);
      return (
        <div key={section.id ?? '__all__'}>
          {section.id !== null && (
            <SubgroupSectionHeader
              name={section.name}
              items={section.items}
              collapsed={collapsed}
              roles={roles}
              opoOff={opoOff}
              onToggle={() => toggleSection(section.id!)}
            />
          )}
          {!collapsed && (
            <SortableContext
              items={section.items.map((a) => a.id)}
              strategy={verticalListSortingStrategy}
            >
              <div>
                {section.items.map((a) => (
                  <BacklogAllocRow
                    key={a.id}
                    alloc={a}
                    scenarioId={scenarioId!}
                    scenarioStatus={(scenario?.status ?? 'draft') as 'draft' | 'approved'}
                    isDraft={isDraft}
                    dragLocked={personSort !== null}
                    compact={compact}
                    flashing={flashingIds.has(a.id)}
                    rowStateClass={rowStateClass(a)}
                    gridTemplate={gridTemplate}
                    gridGap={gridGap}
                    continuationInfo={continuation?.info_by_allocation_id?.[a.id]}
                    teamAssigneeOptions={teamAssigneeOptions}
                    subgroupOptions={hasSubgroups ? subgroupOptions : undefined}
                    roles={roles}
                    opoOff={opoOff}
                    jiraBaseUrl={jiraBaseUrl}
                    resourceTotalForBacklog={resourceSummary?.available_for_backlog_total ?? 0}
                    registerRef={registerRowRef}
                    onToggle={toggleAllocation}
                    onPriorityChange={handlePriorityChange}
                    onAssigneeChange={handleAssigneeChange}
                    onDeveloperChange={handleDeveloperChange}
                    onSubgroupChange={handleSubgroupChange}
                    onOpenBreakdown={handleOpenBreakdown}
                  />
                ))}
              </div>
            </SortableContext>
          )}
        </div>
      );
    })}
    {(allocations ?? []).length === 0 && !allocLoading && (
      <div style={{ padding: 24, textAlign: 'center', color: DARK_THEME.textMuted, fontSize: 13 }}>
        В сценарии нет элементов. Добавьте задачи в бэклог — они появятся автоматически.
      </div>
    )}
    </div>
  </DndContext>
  );
}
