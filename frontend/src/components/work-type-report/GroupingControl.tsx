import { useState } from 'react';
import { Button, Modal, Input, Switch, Dropdown, Tag } from 'antd';
import { PlusOutlined, StarFilled, CloseOutlined } from '@ant-design/icons';
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
  useSortable,
  horizontalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import { restrictToHorizontalAxis } from '@dnd-kit/modifiers';
import { CSS } from '@dnd-kit/utilities';
import { useLayoutList, useCreateLayout, useDeleteLayout } from '../../hooks/useWorkTypeReportLayouts';
import { DARK_THEME } from '../../utils/constants';
import type { GroupingDim } from '../../types/workTypeReport';

// ---- Preset definitions ----
const PRESETS: { label: string; dims: GroupingDim[] }[] = [
  { label: 'По темам', dims: ['theme', 'issue'] },
  { label: 'По сотрудникам', dims: ['employee', 'theme', 'issue'] },
  { label: 'По командам', dims: ['team', 'employee', 'issue'] },
  { label: 'По ролям', dims: ['role', 'employee', 'issue'] },
  { label: 'По проектам', dims: ['project', 'theme', 'issue'] },
];

const DIM_LABELS: Record<GroupingDim, string> = {
  theme: 'Тема',
  team: 'Команда',
  role: 'Роль',
  employee: 'Сотрудник',
  project: 'Проект',
  issue: 'Задача',
};

const ALL_DIMS: GroupingDim[] = ['theme', 'team', 'role', 'employee', 'project', 'issue'];

function dimsEqual(a: GroupingDim[], b: GroupingDim[]): boolean {
  return a.length === b.length && a.every((d, i) => d === b[i]);
}

// ---- Sortable chip ----
interface SortableChipProps {
  id: GroupingDim;
  onRemove: (dim: GroupingDim) => void;
  disabled: boolean;
}

function SortableChip({ id, onRemove, disabled }: SortableChipProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        background: DARK_THEME.darkAccent,
        border: `1px solid ${DARK_THEME.cyanPrimary}`,
        borderRadius: 4,
        padding: '2px 8px',
        fontSize: 12,
        color: DARK_THEME.cyanPrimary,
        cursor: isDragging ? 'grabbing' : 'grab',
        userSelect: 'none',
        opacity: isDragging ? 0.6 : 1,
        zIndex: isDragging ? 999 : undefined,
      }}
    >
      {DIM_LABELS[id]}
      {!disabled && (
        <CloseOutlined
          style={{ fontSize: 10, marginLeft: 2, cursor: 'pointer' }}
          onClick={(e) => {
            e.stopPropagation();
            onRemove(id);
          }}
        />
      )}
    </div>
  );
}

// ---- Main component ----
interface Props {
  workTypeId: string;
  groupingDims: GroupingDim[];
  onChange: (dims: GroupingDim[]) => void;
}

export default function GroupingControl({ workTypeId, groupingDims, onChange }: Props) {
  const { data: layouts = [] } = useLayoutList(workTypeId);
  const createLayout = useCreateLayout();
  const deleteLayout = useDeleteLayout();

  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveDefault, setSaveDefault] = useState(false);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const activePreset = PRESETS.find((p) => dimsEqual(p.dims, groupingDims));

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = groupingDims.indexOf(active.id as GroupingDim);
    const newIndex = groupingDims.indexOf(over.id as GroupingDim);
    if (oldIndex === -1 || newIndex === -1) return;
    onChange(arrayMove(groupingDims, oldIndex, newIndex));
  }

  function removeDim(dim: GroupingDim) {
    if (groupingDims.length <= 1) return;
    onChange(groupingDims.filter((d) => d !== dim));
  }

  const unusedDims = ALL_DIMS.filter((d) => !groupingDims.includes(d));

  function handleSaveLayout() {
    createLayout.mutate(
      {
        work_type_id: workTypeId,
        name: saveName.trim(),
        grouping_dims: groupingDims,
        is_default: saveDefault,
      },
      {
        onSuccess: () => {
          setSaveModalOpen(false);
          setSaveName('');
          setSaveDefault(false);
        },
      },
    );
  }

  return (
    <div
      style={{
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 8,
        padding: '12px 16px',
        marginBottom: 16,
      }}
    >
      {/* Preset chips */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
        {PRESETS.map((p) => {
          const isActive = !!activePreset && dimsEqual(p.dims, activePreset.dims);
          return (
            <Button
              key={p.label}
              size="small"
              type={isActive ? 'primary' : 'default'}
              style={{
                fontSize: 12,
                background: isActive ? DARK_THEME.cyanPrimary : DARK_THEME.darkAccent,
                borderColor: isActive ? DARK_THEME.cyanPrimary : DARK_THEME.border,
                color: isActive ? '#000' : DARK_THEME.textSecondary,
              }}
              onClick={() => onChange(p.dims)}
            >
              {p.label}
            </Button>
          );
        })}
      </div>

      {/* Saved layout chips */}
      {layouts.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          {layouts.map((layout) => (
            <Tag
              key={layout.id}
              closable
              onClose={(e) => {
                e.preventDefault();
                deleteLayout.mutate({ layoutId: layout.id, workTypeId });
              }}
              onClick={() => onChange(layout.grouping_dims)}
              style={{
                cursor: 'pointer',
                background: DARK_THEME.darkAccent,
                border: `1px solid ${DARK_THEME.border}`,
                color: DARK_THEME.textSecondary,
                fontSize: 12,
              }}
            >
              {layout.is_default && (
                <StarFilled style={{ color: DARK_THEME.yellow, marginRight: 4, fontSize: 10 }} />
              )}
              {layout.name}
            </Tag>
          ))}
        </div>
      )}

      {/* Pivot chip row (dnd) + add button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: DARK_THEME.textMuted, flexShrink: 0 }}>
          Порядок:
        </span>
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToHorizontalAxis]}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={groupingDims} strategy={horizontalListSortingStrategy}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'nowrap', alignItems: 'center' }}>
              {groupingDims.map((dim) => (
                <SortableChip
                  key={dim}
                  id={dim}
                  onRemove={removeDim}
                  disabled={groupingDims.length <= 1}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>

        {unusedDims.length > 0 && (
          <Dropdown
            menu={{
              items: unusedDims.map((d) => ({
                key: d,
                label: DIM_LABELS[d],
                onClick: () => onChange([...groupingDims, d]),
              })),
            }}
            trigger={['click']}
          >
            <Button
              size="small"
              icon={<PlusOutlined />}
              style={{
                fontSize: 12,
                background: DARK_THEME.darkAccent,
                borderColor: DARK_THEME.border,
                color: DARK_THEME.textMuted,
              }}
            />
          </Dropdown>
        )}

        <Button
          size="small"
          style={{
            marginLeft: 'auto',
            fontSize: 12,
            background: DARK_THEME.darkAccent,
            borderColor: DARK_THEME.border,
            color: DARK_THEME.yellow,
          }}
          icon={<StarFilled style={{ fontSize: 11 }} />}
          onClick={() => setSaveModalOpen(true)}
        >
          Сохранить как...
        </Button>
      </div>

      {/* Save Modal */}
      <Modal
        title="Сохранить макет"
        open={saveModalOpen}
        onOk={handleSaveLayout}
        onCancel={() => {
          setSaveModalOpen(false);
          setSaveName('');
          setSaveDefault(false);
        }}
        okText="Сохранить"
        cancelText="Отмена"
        confirmLoading={createLayout.isPending}
        okButtonProps={{ disabled: !saveName.trim() }}
      >
        <div style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 6, fontSize: 13 }}>Название</div>
          <Input
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            placeholder="Например: Мой анализ"
            autoFocus
            onPressEnter={() => saveName.trim() && handleSaveLayout()}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Switch checked={saveDefault} onChange={setSaveDefault} size="small" />
          <span style={{ fontSize: 13 }}>Сделать макетом по умолчанию</span>
        </div>
      </Modal>
    </div>
  );
}
