import { Space } from 'antd';
import ScopeOverview from './ScopeOverview';
import TaskSectionsTab from './TaskSectionsTab';

export default function ScopeAdmin() {
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <ScopeOverview />
      <TaskSectionsTab />
    </Space>
  );
}
