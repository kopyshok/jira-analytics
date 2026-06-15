import { Collapse, Table, Typography } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { projectColumns } from './projectColumns';
import type { TeamAvailabilityData } from '../../types/desk';

export default function TeamAvailabilityWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<TeamAvailabilityData>(
    token,
    'team_availability',
  );
  const members = (data?.members ?? []).filter((m) => m.projects.length > 0);

  const items = members.map((m) => ({
    key: m.id,
    label: (
      <span>
        {m.display_name}{' '}
        <Typography.Text type="secondary">({m.projects.length})</Typography.Text>
      </span>
    ),
    children: (
      <Table
        rowKey={(r) => `${m.id}-${r.key ?? ''}-${r.start_date ?? ''}`}
        size="small"
        columns={projectColumns()}
        dataSource={m.projects}
        pagination={false}
      />
    ),
  }));

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={members.length === 0}
      emptyText="Нет занятости команды"
    >
      <Collapse size="small" items={items} defaultActiveKey={members.slice(0, 1).map((m) => m.id)} />
    </WidgetShell>
  );
}
