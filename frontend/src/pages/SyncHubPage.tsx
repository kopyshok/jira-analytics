import { useState } from 'react';
import { Tabs, Typography, Button } from 'antd';
import { Space } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import PipelineRunner from '../components/sync/PipelineRunner';
import SyncSchedule from '../components/sync/SyncSchedule';
import SyncHistory from '../components/sync/SyncHistory';
import SyncAdvanced from '../components/sync/SyncAdvanced';
import HelpDrawer from '../components/shared/HelpDrawer';
import { useJiraTeams } from '../hooks/useSync';
import syncHelp from '../../../docs/help/sync.md?raw';

export default function SyncHubPage() {
  const jiraTeams = useJiraTeams();
  const teams = jiraTeams.data ?? [];
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <Space orientation="vertical" style={{ width: '100%' }} size="middle">
      <section
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <Typography.Title level={2} style={{ margin: 0 }}>
          Синхронизация
        </Typography.Title>
        <Button
          type="text"
          icon={<QuestionCircleOutlined />}
          onClick={() => setHelpOpen(true)}
          title="Справка по разделу"
        >
          Справка
        </Button>
      </section>
      <HelpDrawer
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title="Синхронизация с Jira"
        content={syncHelp}
        imageBase="/help-assets/"
      />
      <Tabs
        items={[
          {
            key: 'pipeline',
            label: 'Синхронизация',
            children: (
              <Space orientation="vertical" style={{ width: '100%' }} size="middle">
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
    </Space>
  );
}
