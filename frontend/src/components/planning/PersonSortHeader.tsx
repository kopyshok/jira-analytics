import type { ReactNode } from 'react';
import { CaretDownOutlined, CaretUpOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';
import type { PersonSort, PersonSortKey } from '../../utils/allocationSort';

/** Заголовок колонки с людьми: щелчок — А→Я, Я→А, сброс. */
export default function SortableHeader({
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

