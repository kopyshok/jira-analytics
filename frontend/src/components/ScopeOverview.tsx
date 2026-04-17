import { Card, Space, Tag } from 'antd';
import { Typography } from 'antd';
import { useScopeProjects, useRemoveScopeProject } from '../hooks/useScope';

const { Text } = Typography;

export default function ScopeOverview() {
  const { data } = useScopeProjects();
  const remove = useRemoveScopeProject();

  return (
    <Card title="Текущий scope" size="small">
      {(!data || data.length === 0) ? (
        <Text type="secondary">Scope пуст — при синхронизации будут загружены все проекты</Text>
      ) : (
        <Space wrap>
          {data.map(p => (
            <Tag
              key={p.id}
              closable
              onClose={(e) => { e.preventDefault(); remove.mutate(p.jira_project_key); }}
              color="blue"
            >
              {p.jira_project_key}
            </Tag>
          ))}
        </Space>
      )}
    </Card>
  );
}
