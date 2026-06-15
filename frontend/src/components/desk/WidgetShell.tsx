import type { ReactNode } from 'react';
import { Card, Skeleton, Empty, Alert } from 'antd';

interface WidgetShellProps {
  title: string;
  isLoading: boolean;
  isError: boolean;
  isEmpty: boolean;
  emptyText?: string;
  children: ReactNode;
}

/** Единая оболочка виджета стола: заголовок, скелетон, пусто, ошибка. */
export default function WidgetShell({
  title,
  isLoading,
  isError,
  isEmpty,
  emptyText = 'Нет данных',
  children,
}: WidgetShellProps) {
  return (
    <Card title={title} size="small" style={{ height: '100%' }}>
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : isError ? (
        <Alert type="warning" showIcon message="Не удалось загрузить данные" />
      ) : isEmpty ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
      ) : (
        children
      )}
    </Card>
  );
}
