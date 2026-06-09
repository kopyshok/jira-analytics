import { useMemo } from 'react';
import { Button, Tooltip } from 'antd';
import { EyeOutlined, EyeInvisibleOutlined, DragOutlined } from '@ant-design/icons';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  useAnalyticsLayout,
  DEFAULT_LAYOUT,
  ALL_LEVELS,
  LEVEL_LABELS,
  type AnalyticsLevel,
} from '../../hooks/useAnalyticsLayout';

const PRESETS: { key: string; label: string; order: AnalyticsLevel[]; hidden: AnalyticsLevel[] }[] = [
  {
    key: 'default',
    label: 'Стандарт',
    order: ['team', 'role', 'employee', 'work_type', 'category', 'issue'],
    hidden: [],
  },
  {
    key: 'people',
    label: 'По людям',
    order: ['employee', 'category', 'issue'],
    hidden: ['team', 'role', 'work_type'],
  },
  {
    key: 'categories',
    label: 'По категориям',
    order: ['category', 'work_type', 'issue'],
    hidden: ['team', 'role', 'employee'],
  },
  {
    key: 'work_types',
    label: 'По видам работ',
    order: ['work_type', 'category', 'issue'],
    hidden: ['team', 'role', 'employee'],
  },
];

interface SortableLevelProps {
  level: AnalyticsLevel;
  hidden: boolean;
  onToggleVisible: (level: AnalyticsLevel) => void;
}

function SortableLevel({ level, hidden, onToggleVisible }: SortableLevelProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: level });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    background: hidden ? 'rgba(68, 90, 130, 0.18)' : '#162f54',
    border: '1px solid rgba(255,255,255,0.06)',
    borderRadius: 6,
    padding: '8px 12px',
    marginBottom: 6,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    opacity: hidden ? 0.55 : 1,
    cursor: isDragging ? 'grabbing' : 'default',
  };
  return (
    <div ref={setNodeRef} style={style}>
      <span {...attributes} {...listeners} style={{ cursor: 'grab', color: 'var(--text-muted, #7e94b8)' }}>
        <DragOutlined />
      </span>
      <span style={{ flex: 1, color: 'var(--text, #e6edf7)' }}>{LEVEL_LABELS[level]}</span>
      <Tooltip title={hidden ? 'Показать уровень' : 'Скрыть уровень'}>
        <Button
          type="text"
          size="small"
          icon={hidden ? <EyeInvisibleOutlined /> : <EyeOutlined />}
          onClick={() => onToggleVisible(level)}
          disabled={level === 'issue'}
        />
      </Tooltip>
    </div>
  );
}

export default function GroupingEditor() {
  const { layout, save, isSaving } = useAnalyticsLayout();
  const order = layout.group_order && layout.group_order.length > 0 ? layout.group_order : DEFAULT_LAYOUT.group_order;
  const hidden = useMemo(() => new Set(layout.hidden_levels ?? []), [layout.hidden_levels]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const oldIndex = order.indexOf(active.id as AnalyticsLevel);
    const newIndex = order.indexOf(over.id as AnalyticsLevel);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(order, oldIndex, newIndex);
    save({ ...layout, group_order: next, active_preset: 'custom' });
  };

  const toggleHidden = (level: AnalyticsLevel) => {
    const nextHidden = new Set(hidden);
    if (nextHidden.has(level)) nextHidden.delete(level);
    else nextHidden.add(level);
    save({ ...layout, hidden_levels: Array.from(nextHidden), active_preset: 'custom' });
  };

  const applyPreset = (preset: typeof PRESETS[number]) => {
    save({
      ...layout,
      group_order: preset.order.concat(ALL_LEVELS.filter((l) => !preset.order.includes(l))),
      hidden_levels: preset.hidden,
      active_preset: preset.key,
    });
  };

  const visibleOrder = useMemo(() => order.filter((l) => !hidden.has(l)), [order, hidden]);
  const hiddenOrder = useMemo(() => order.filter((l) => hidden.has(l)), [order, hidden]);

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {PRESETS.map((p) => (
          <Button
            key={p.key}
            size="small"
            type={layout.active_preset === p.key ? 'primary' : 'default'}
            onClick={() => applyPreset(p)}
            disabled={isSaving}
          >
            {p.label}
          </Button>
        ))}
      </div>

      <div style={{ fontSize: 11, color: 'var(--text-muted, #7e94b8)', textTransform: 'uppercase', marginBottom: 6 }}>
        Активные уровни
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={visibleOrder} strategy={verticalListSortingStrategy}>
          {visibleOrder.map((l) => (
            <SortableLevel key={l} level={l} hidden={false} onToggleVisible={toggleHidden} />
          ))}
        </SortableContext>
      </DndContext>

      {hiddenOrder.length > 0 && (
        <>
          <div style={{ fontSize: 11, color: 'var(--text-muted, #7e94b8)', textTransform: 'uppercase', marginTop: 16, marginBottom: 6 }}>
            Скрытые
          </div>
          {hiddenOrder.map((l) => (
            <SortableLevel key={l} level={l} hidden onToggleVisible={toggleHidden} />
          ))}
        </>
      )}
    </div>
  );
}
