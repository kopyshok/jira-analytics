import { Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CheckCircleTwoTone, ClockCircleOutlined } from '@ant-design/icons';
import type { FeedbackItem } from '../../api/feedback';

interface Props {
  items: FeedbackItem[];
  loading?: boolean;
  showAuthor?: boolean;
  showReadStatus?: boolean;
  rowSelection?: {
    selectedRowKeys: string[];
    onChange: (keys: string[]) => void;
  };
  onRowClick?: (item: FeedbackItem) => void;
}

export default function FeedbackList({
  items,
  loading,
  showAuthor = false,
  showReadStatus = false,
  rowSelection,
  onRowClick,
}: Props) {
  const cols: ColumnsType<FeedbackItem> = [
    {
      title: 'Тип',
      dataIndex: 'kind',
      width: 90,
      render: (k: string) => (
        <Tag color={k === 'bug' ? 'red' : 'blue'}>{k === 'bug' ? 'Баг' : 'Идея'}</Tag>
      ),
    },
    {
      title: 'Заголовок',
      dataIndex: 'title',
      render: (t: string, r) => (
        <div>
          <Typography.Text strong>{t}</Typography.Text>
          <div style={{ color: '#888', fontSize: 12 }}>
            {r.body.slice(0, 120)}
            {r.body.length > 120 ? '…' : ''}
          </div>
        </div>
      ),
    },
    ...(showAuthor
      ? ([
          {
            title: 'Автор',
            dataIndex: ['author', 'display_name'],
            width: 160,
          },
        ] as ColumnsType<FeedbackItem>)
      : []),
    {
      title: 'Создан',
      dataIndex: 'created_at',
      width: 160,
      render: (s: string) => new Date(s).toLocaleString('ru-RU'),
    },
    ...(showReadStatus
      ? ([
          {
            title: 'Статус',
            dataIndex: 'read_at',
            width: 110,
            render: (s: string | null) =>
              s ? (
                <Tooltip title={`Прочитано ${new Date(s).toLocaleString('ru-RU')}`}>
                  <Tag icon={<CheckCircleTwoTone twoToneColor="#52c41a" />} color="success">
                    Прочитано
                  </Tag>
                </Tooltip>
              ) : (
                <Tag icon={<ClockCircleOutlined />} color="orange">
                  Новый
                </Tag>
              ),
          },
        ] as ColumnsType<FeedbackItem>)
      : []),
  ];

  const tableProps: Parameters<typeof Table<FeedbackItem>>[0] = {
    rowKey: 'id',
    size: 'small',
    dataSource: items,
    columns: cols,
    loading,
    pagination: { pageSize: 25, showSizeChanger: false },
    onRow: onRowClick
      ? (r) => ({ onClick: () => onRowClick(r), style: { cursor: 'pointer' } })
      : undefined,
  };

  if (rowSelection) {
    tableProps.rowSelection = {
      selectedRowKeys: rowSelection.selectedRowKeys,
      onChange: (keys) => rowSelection.onChange(keys as string[]),
    };
  }

  return <Table<FeedbackItem> {...tableProps} />;
}
