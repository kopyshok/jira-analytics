import { Tabs } from 'antd';
import { Space } from 'antd';
import PipelineRunner from '../components/sync/PipelineRunner';
import SyncSchedule from '../components/sync/SyncSchedule';
import SyncHistory from '../components/sync/SyncHistory';
import SyncAdvanced from '../components/sync/SyncAdvanced';
import { useJiraTeams } from '../hooks/useSync';

export default function SyncHubPage() {
  const jiraTeams = useJiraTeams();
  const teams = jiraTeams.data ?? [];

  return (
    <Tabs
      items={[
        {
          key: 'pipeline',
          label: 'Синхронизация',
          children: (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <PipelineRunner teams={teams} />
              <SyncHistory />
            </Space>
          ),
        },
        {
          key: 'schedule',
          label: 'Расписание',
          children: <SyncSchedule />,
        },
        {
          key: 'advanced',
          label: 'Дополнительно',
          children: <SyncAdvanced />,
        },
      ]}
    />
  );
}
