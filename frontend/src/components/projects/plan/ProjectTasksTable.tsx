import React from 'react';
import { Empty, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { PlanChild } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

const columns: ColumnsType<PlanChild> = [
  {
    title: 'Ключ',
    dataIndex: 'key',
    width: 130,
    render: (key: string, row) =>
      row.jira_url ? (
        <a href={row.jira_url} target="_blank" rel="noreferrer">{key}</a>
      ) : key,
  },
  {
    title: 'Название',
    dataIndex: 'title',
    ellipsis: true,
    render: (title: string | null) => title ?? '—',
  },
  {
    title: 'Статус',
    dataIndex: 'status',
    width: 160,
    render: (status: string | null) => status ?? '—',
  },
  {
    title: 'Часы',
    dataIndex: 'hours',
    width: 90,
    align: 'right',
    sorter: (a, b) => a.hours - b.hours,
    render: (hours: number) => `${Math.round(hours)} ч`,
  },
];

export const ProjectTasksTable: React.FC<{ children: PlanChild[] }> = ({ children }) => {
  if (children.length === 0) {
    return (
      <Empty
        description={<span style={{ color: DARK_THEME.textMuted }}>Нет задач</span>}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }
  return (
    <Table
      rowKey="key"
      size="small"
      pagination={false}
      columns={columns}
      dataSource={children}
    />
  );
};
