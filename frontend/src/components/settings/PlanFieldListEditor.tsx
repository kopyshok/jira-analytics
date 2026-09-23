import { useState } from 'react';
import { Button, Segmented, Select, Tooltip, Typography } from 'antd';
import {
  ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined,
} from '@ant-design/icons';
import {
  fieldIdHint, moveEntry, parsePlanFieldSetting, serializePlanFieldSetting,
  type PlanFieldEntry, type PlanFieldKind,
} from '../../utils/planFieldSources';

export interface JiraFieldOption {
  value: string;
  label: string;
  name: string;
}

interface Props {
  /** Значение настройки роли: JSON-список или старая строка с одним полем. */
  value: string;
  onChange: (next: string) => void;
  /** Поля Jira; пусто, пока список не подгружен. */
  options: JiraFieldOption[];
  loading: boolean;
  /** Открыли выпадающий список — подгрузить поля Jira. */
  onOpen: () => void;
}

const KIND_OPTIONS: { label: string; value: PlanFieldKind }[] = [
  { label: 'Альтернатива', value: 'alt' },
  { label: 'Слагаемое', value: 'sum' },
];

const EMPTY_ROW: PlanFieldEntry = { field_id: '', kind: 'alt' };

/** Список полей Jira для одной роли. Порядок важен: при споре до выбора
 *  действует верхнее поле. Пустые строки живут только здесь, в настройку не пишутся. */
export default function PlanFieldListEditor({ value, onChange, options, loading, onOpen }: Props) {
  const [rows, setRows] = useState<PlanFieldEntry[]>(() => {
    const parsed = parsePlanFieldSetting(value);
    return parsed.length ? parsed : [EMPTY_ROW];
  });
  const nameById = new Map(options.map((o) => [o.value, o.name]));
  // Пока список Jira не подгружен, название берём из самой настройки.
  const nameOf = (id: string) => nameById.get(id) ?? rows.find((r) => r.field_id === id)?.name ?? null;
  const fieldLabel = (id: string) => {
    const name = nameOf(id);
    if (!name) return id;
    return (
      <span>
        {name} <Typography.Text type="secondary">· {fieldIdHint(id)}</Typography.Text>
      </span>
    );
  };

  const update = (next: PlanFieldEntry[]) => {
    // Названия записываем в настройку: по ним подписаны варианты в споре.
    const named = next.map((r) => ((r.name || !nameById.has(r.field_id)) ? r : { ...r, name: nameById.get(r.field_id) }));
    setRows(named);
    onChange(serializePlanFieldSetting(named));
  };
  const patchRow = (i: number, patch: Partial<PlanFieldEntry>) =>
    update(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-start' }}>
      {rows.map((row, i) => {
        // Поле, уже выбранное в другой строке роли, второй раз не предлагаем.
        const taken = new Set(rows.filter((_, j) => j !== i).map((r) => r.field_id));
        return (
          <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center', width: '100%' }}>
            <Select
              style={{ flex: '1 1 200px', minWidth: 180, maxWidth: 340 }}
              value={row.field_id || undefined}
              showSearch={{ optionFilterProp: 'label' }}
              allowClear
              placeholder="Выберите поле Jira"
              options={options.map((o) => ({ ...o, disabled: taken.has(o.value) }))}
              labelRender={({ value: v }) => fieldLabel(String(v))}
              optionRender={(o) => fieldLabel(String(o.value))}
              loading={loading}
              onOpenChange={(open) => { if (open) onOpen(); }}
              onChange={(v?: string) => patchRow(i, {
                field_id: v ?? '',
                name: v ? (nameById.get(v) ?? null) : null,
              })}
            />
            <Segmented<PlanFieldKind>
              size="small"
              value={row.kind}
              options={KIND_OPTIONS}
              onChange={(kind) => patchRow(i, { kind })}
            />
            <Tooltip title="Выше">
              <Button
                size="small"
                icon={<ArrowUpOutlined />}
                aria-label="Поднять поле выше"
                disabled={i === 0}
                onClick={() => update(moveEntry(rows, i, -1))}
              />
            </Tooltip>
            <Tooltip title="Ниже">
              <Button
                size="small"
                icon={<ArrowDownOutlined />}
                aria-label="Опустить поле ниже"
                disabled={i === rows.length - 1}
                onClick={() => update(moveEntry(rows, i, 1))}
              />
            </Tooltip>
            <Tooltip title="Убрать поле">
              <Button
                size="small"
                icon={<DeleteOutlined />}
                aria-label="Убрать поле"
                onClick={() => update(rows.filter((_, j) => j !== i))}
              />
            </Tooltip>
          </div>
        );
      })}
      <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={() => setRows([...rows, EMPTY_ROW])}>
        Добавить поле
      </Button>
    </div>
  );
}
