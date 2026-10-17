import type { ReactNode } from 'react';
import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import {
  CaretDownOutlined, CaretUpOutlined, CheckSquareTwoTone, ClockCircleOutlined,
  CodeOutlined, FlagFilled, ShopOutlined, UserOutlined,
} from '@ant-design/icons';
import BacklogAllocRow from './BacklogAllocRow';
import SubgroupSectionHeader from './SubgroupSectionHeader';
import NeighborsTakenBanner from './NeighborsTakenBanner';
import { DARK_THEME } from '../../utils/constants';
import { nextPersonSort, type PersonSort, type PersonSortKey } from '../../utils/allocationSort';
import type { PlanningPageModel } from '../../hooks/usePlanningPage';

const GRID = '24px 36px 60px minmax(220px, 1fr) 130px 130px 180px 260px 90px';
// Та же сетка + колонка «Группа» после разработчика — для команд с делением.
const GRID_WITH_SUBGROUP = '24px 36px 60px minmax(220px, 1fr) 130px 130px 140px 180px 260px 90px';
// Таблица обложки: «Вкл», «Приоритет», отметка состояния, идея, люди, заказчик,
// часы по ролям, всего. Колонки строки переставляются стилями обложки.
const GRID_TABLE = '28px 64px 12px minmax(180px, 1fr) 100px 104px 112px 160px 60px';
const GRID_TABLE_WITH_SUBGROUP = '28px 64px 12px minmax(180px, 1fr) 100px 104px 104px 112px 160px 60px';
const GRID_GAP = 8;
// Уже этой ширины список прокручивается вбок, а не сжимает «Идею» до нуля:
// колонки (у «Идеи» — её минимум) + зазоры + поля строки и полоса отметки слева.
const gridMinWidth = (tpl: string) => {
  const px = [...tpl.matchAll(/(\d+)px/g)].map((m) => Number(m[1]));
  return px.reduce((sum, w) => sum + w, 0) + (px.length - 1) * GRID_GAP + 32;
};

/** Заголовок колонки с людьми: щелчок — А→Я, Я→А, сброс. */
function SortableHeader({
  sortKey, sort, onSort, children,
}: {
  sortKey: PersonSortKey;
  sort: PersonSort | null;
  onSort: (key: PersonSortKey) => void;
  children: ReactNode;
}) {
  const dir = sort?.key === sortKey ? sort.dir : null;
  return (
    <span
      role="button"
      tabIndex={0}
      title="Сортировать: А→Я, Я→А, сброс"
      onClick={() => onSort(sortKey)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSort(sortKey);
        }
      }}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer', userSelect: 'none' }}
    >
      {children}
      {dir === 'asc' && <CaretUpOutlined style={{ color: DARK_THEME.cyanPrimary }} />}
      {dir === 'desc' && <CaretDownOutlined style={{ color: DARK_THEME.cyanPrimary }} />}
    </span>
  );
}

/**
 * Список элементов бэклога сценария: шапка, секции групп, строки с
 * перетаскиванием. card — как в Aurora (шапка значками, плашка про соседей
 * внутри); table — таблица обложки (шапка словами, плашка — снаружи).
 */
export default function ScenarioBacklogTable({ vm, variant = 'card' }: {
  vm: PlanningPageModel;
  variant?: 'card' | 'table';
}) {
  const {
    scenarioId, scenario, isDraft, compact, hasSubgroups, opoOff, roles,
    personSort, setPersonSort, handleDragEnd, shownSections, collapsedSections, toggleSection,
    flashingIds, rowStateClass, continuation, teamAssigneeOptions, subgroupOptions, jiraBaseUrl,
    resourceSummary, registerRowRef, toggleAllocation, handlePriorityChange, handleAssigneeChange,
    handleDeveloperChange, handleSubgroupChange, handleOpenBreakdown, allocations, allocLoading,
    neighborsTakenIds, onlyNeighborsTaken, setOnlyNeighborsTaken,
  } = vm;
  const table = variant === 'table';
  const gridTemplate = table
    ? (hasSubgroups ? GRID_TABLE_WITH_SUBGROUP : GRID_TABLE)
    : (hasSubgroups ? GRID_WITH_SUBGROUP : GRID);
  const onSort = (k: PersonSortKey) => setPersonSort((s) => nextPersonSort(s, k));
  const roleLabels = opoOff ? ['АН', 'ПР', 'ТС'] : ['АН', 'ПР', 'ТС', 'ОПЭ'];

  const header = table ? (
    <div className="bl-head" style={{ gridTemplateColumns: gridTemplate, columnGap: GRID_GAP }}>
      <span title="Включено в сценарий">Вкл</span>
      <span>Приоритет</span>
      <span aria-hidden />
      <span>Идея</span>
      <SortableHeader sortKey="analyst" sort={personSort} onSort={onSort}>Аналитик</SortableHeader>
      <SortableHeader sortKey="developer" sort={personSort} onSort={onSort}>Разработчик</SortableHeader>
      {hasSubgroups && <span>Группа</span>}
      <span>Заказчик</span>
      <div className="bl-head-hours">
        {roleLabels.map((l) => <span key={l}>{l}</span>)}
      </div>
      <span className="bl-head-total">Всего часов</span>
    </div>
  ) : (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: gridTemplate,
        columnGap: GRID_GAP,
        padding: compact ? '4px 14px' : '8px 14px',
        borderBottom: `1px solid ${DARK_THEME.border}`,
        background: DARK_THEME.darkAccent,
        fontSize: 13,
        fontWeight: 700,
        color: DARK_THEME.textPrimary,
        textTransform: 'uppercase',
        letterSpacing: 0.6,
      }}
    >
      <span aria-hidden style={{ textAlign: 'center' }} />
      <span title="Включено в сценарий" style={{ textAlign: 'center' }}>
        <CheckSquareTwoTone
          className="icon-tick"
          twoToneColor={DARK_THEME.cyanPrimary}
          style={{ fontSize: 16 }}
        />
      </span>
      <span title="Приоритет" style={{ textAlign: 'center' }}>
        <FlagFilled className="flag-wave" style={{ color: DARK_THEME.cyanPrimary, fontSize: 16 }} />
      </span>
      <span>Идея</span>
      <SortableHeader sortKey="analyst" sort={personSort} onSort={onSort}>
        <UserOutlined className="icon-bob" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
        Аналитик
      </SortableHeader>
      <SortableHeader sortKey="developer" sort={personSort} onSort={onSort}>
        <CodeOutlined style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
        Разработчик
      </SortableHeader>
      {hasSubgroups && <span>Группа</span>}
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <ShopOutlined className="icon-wiggle" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
        Заказчик
      </span>
      <div style={{ display: 'flex', gap: 4 }}>
        {roleLabels.map((l) => (
          <span key={l} style={{ flex: 1, minWidth: 52, textAlign: 'center' }}>{l}</span>
        ))}
      </div>
      <span style={{ textAlign: 'right', display: 'inline-flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
        <ClockCircleOutlined className="icon-spin-slow" style={{ color: DARK_THEME.cyanPrimary, fontSize: 14 }} />
        Всего часов
      </span>
    </div>
  );

  return (
    <>
      {!table && neighborsTakenIds.size > 0 && (
        <NeighborsTakenBanner
          count={neighborsTakenIds.size}
          onlyThem={onlyNeighborsTaken}
          onOnlyThemChange={setOnlyNeighborsTaken}
        />
      )}
      <div style={{ overflowX: 'auto' }} className={table ? 'bl-scroll' : undefined}>
      <div style={{ minWidth: gridMinWidth(gridTemplate) }}>
      {header}
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
                        plainHours={table}
                        flashing={flashingIds.has(a.id)}
                        rowStateClass={rowStateClass(a)}
                        gridTemplate={gridTemplate}
                        gridGap={GRID_GAP}
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
      </div>
      </div>
    </>
  );
}
