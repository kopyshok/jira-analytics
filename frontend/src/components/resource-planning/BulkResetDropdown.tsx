import { App, Button, Dropdown, Modal } from 'antd';
import type { MenuProps } from 'antd';
import { DownOutlined, ReloadOutlined } from '@ant-design/icons';
import { useBulkClear } from '../../hooks/useResourcePlanning';
import type { BulkClearMode, ResetCounts } from '../../api/resourcePlanning';

interface Props {
  planId: string | null;
  counts: ResetCounts;
}

const MODE_LABELS: Record<BulkClearMode, string> = {
  dates: 'Сбросить закреплённые даты',
  employees: 'Сбросить закреплённых исполнителей',
  predecessors: 'Сбросить связи предшественников',
  all: 'Сбросить всё к первоначальному виду',
};

const MODE_DESCRIPTIONS: Record<BulkClearMode, (n: number) => string> = {
  dates: (n) => `Снять ручную фиксацию даты у ${n} фаз. Планировщик пересчитает окна.`,
  employees: (n) => `Снять закрепление исполнителя у ${n} фаз. Планировщик подберёт заново.`,
  predecessors: (n) => `Удалить ручные связи у ${n} фаз. Восстановится стандартная цепочка.`,
  all: () => 'Снять все ручные правки: даты, исполнителей, связи. План пересчитается полностью.',
};

const TOTAL = (c: ResetCounts) => c.pinned_dates + c.pinned_employees + c.edited_predecessors;

export default function BulkResetDropdown({ planId, counts }: Props) {
  const { message } = App.useApp();
  const bulkClear = useBulkClear(planId);

  const countFor = (mode: BulkClearMode): number => {
    if (mode === 'dates') return counts.pinned_dates;
    if (mode === 'employees') return counts.pinned_employees;
    if (mode === 'predecessors') return counts.edited_predecessors;
    return TOTAL(counts);
  };

  const handleClick = (mode: BulkClearMode) => {
    const n = countFor(mode);
    if (n === 0 && mode !== 'all') return;
    Modal.confirm({
      title: MODE_LABELS[mode],
      content: MODE_DESCRIPTIONS[mode](n),
      okText: 'Сбросить',
      cancelText: 'Отмена',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const res = await bulkClear.mutateAsync(mode);
          message.success(`Фаз сброшено: ${res.cleared_count}`);
        } catch {
          message.error('Ошибка сброса');
        }
      },
    });
  };

  const items: MenuProps['items'] = [
    {
      key: 'dates',
      label: `${MODE_LABELS.dates} (${counts.pinned_dates})`,
      disabled: counts.pinned_dates === 0,
      onClick: () => handleClick('dates'),
    },
    {
      key: 'employees',
      label: `${MODE_LABELS.employees} (${counts.pinned_employees})`,
      disabled: counts.pinned_employees === 0,
      onClick: () => handleClick('employees'),
    },
    {
      key: 'predecessors',
      label: `${MODE_LABELS.predecessors} (${counts.edited_predecessors})`,
      disabled: counts.edited_predecessors === 0,
      onClick: () => handleClick('predecessors'),
    },
    { type: 'divider' },
    {
      key: 'all',
      label: MODE_LABELS.all,
      danger: true,
      onClick: () => handleClick('all'),
    },
  ];

  return (
    <Dropdown menu={{ items }} trigger={['click']} disabled={!planId}>
      <Button size="small" icon={<ReloadOutlined />} loading={bulkClear.isPending}>
        Сбросить <DownOutlined />
      </Button>
    </Dropdown>
  );
}
