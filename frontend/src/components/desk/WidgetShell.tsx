import type { ReactNode } from 'react';
import { Skeleton } from 'antd';

interface WidgetShellProps {
  title: string;
  isLoading: boolean;
  isError: boolean;
  isEmpty: boolean;
  emptyText?: string;
  children: ReactNode;
}

/** Единая оболочка виджета стола: тихий заголовок с cyan-точкой, мягкая
 *  неоморфная подложка; состояния загрузки / пусто / ошибка. */
export default function WidgetShell({
  title,
  isLoading,
  isError,
  isEmpty,
  emptyText = 'Нет данных',
  children,
}: WidgetShellProps) {
  return (
    <div className="desk-zone">
      <div className="desk-zone-title">
        <span className="desk-zone-dot" />
        {title}
      </div>
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : isError ? (
        <div className="desk-error">Не удалось загрузить данные</div>
      ) : isEmpty ? (
        <div className="desk-empty">{emptyText}</div>
      ) : (
        children
      )}
    </div>
  );
}
