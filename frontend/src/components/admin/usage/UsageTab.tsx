import { useState } from 'react';
import { Radio, Space, Tabs } from 'antd';
import UsageKpiBar from './UsageKpiBar';
import UsageUsersTable from './UsageUsersTable';
import UsagePagesTable from './UsagePagesTable';
import UsageMatrix from './UsageMatrix';
import UsageTimeline from './UsageTimeline';
import UsageActionsTable from './UsageActionsTable';

export default function UsageTab() {
  const [days, setDays] = useState<number>(30);

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <UsageKpiBar />
      <Radio.Group
        value={days}
        onChange={(e) => setDays(e.target.value)}
        optionType="button"
        options={[
          { label: '7 дней', value: 7 },
          { label: '30 дней', value: 30 },
          { label: '90 дней', value: 90 },
        ]}
      />
      <Tabs
        items={[
          {
            key: 'users',
            label: 'Пользователи',
            children: <UsageUsersTable days={days} />,
          },
          {
            key: 'pages',
            label: 'Разделы',
            children: <UsagePagesTable days={days} />,
          },
          {
            key: 'matrix',
            label: 'Кто в каких разделах',
            children: <UsageMatrix days={days} />,
          },
          {
            key: 'timeline',
            label: 'Динамика',
            children: <UsageTimeline days={days} />,
          },
          {
            key: 'actions',
            label: 'Действия',
            children: <UsageActionsTable days={days} />,
          },
        ]}
      />
    </Space>
  );
}
