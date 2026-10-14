import { Table, Tag, Typography } from 'antd';
import type { ProbeItem } from '../../../api/jiraMigration';

export default function ProbeSection({ items }: { items: ProbeItem[] }) {
  return (
    <>
      <Typography.Paragraph type="secondary">
        Каждый запрос, нужный синхронизации, проверен на новой Jira.
        Если не работает обязательный, отчёт не строится и применить переезд нельзя.
      </Typography.Paragraph>
      <Table<ProbeItem>
        rowKey="code"
        size="small"
        pagination={false}
        dataSource={items}
        columns={[
          { title: 'Проверка', dataIndex: 'title' },
          {
            title: 'Обязательная',
            dataIndex: 'essential',
            width: 130,
            render: (essential: boolean) => (essential ? 'Да' : 'Нет'),
          },
          {
            title: 'Результат',
            dataIndex: 'ok',
            width: 150,
            render: (ok: boolean, row) => {
              if (ok) return <Tag color="green">Работает</Tag>;
              return row.essential
                ? <Tag color="red">Не работает</Tag>
                : <Tag color="orange">Предупреждение</Tag>;
            },
          },
          { title: 'Подробности', dataIndex: 'detail' },
        ]}
      />
    </>
  );
}
