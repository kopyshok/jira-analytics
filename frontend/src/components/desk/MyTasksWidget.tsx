import { Table } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { projectColumns } from './projectColumns';
import type { MyTasksData } from '../../types/desk';

export default function MyTasksWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<MyTasksData>(token, 'my_tasks');
  const projects = data?.projects ?? [];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={projects.length === 0}
      emptyText="Нет проектов"
    >
      <Table
        rowKey={(r) => `${r.key ?? ''}-${r.start_date ?? ''}-${r.title ?? ''}`}
        size="small"
        columns={projectColumns()}
        dataSource={projects}
        pagination={false}
        scroll={{ y: 320 }}
      />
    </WidgetShell>
  );
}
