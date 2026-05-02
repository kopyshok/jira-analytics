import { useNavigate, useParams } from 'react-router';
import { Empty } from 'antd';
import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { key } = useParams<{ key?: string }>();

  const handleSelect = (selectedKey: string) => {
    navigate(`/projects/${encodeURIComponent(selectedKey)}`);
  };

  return (
    <div
      style={{
        display: 'flex',
        height: 'calc(100vh - 64px)',
        background: '#0d1c33',
        overflow: 'hidden',
      }}
    >
      <ProjectsList selectedKey={key ?? null} onSelect={handleSelect} />

      {key ? (
        <ProjectDetailPanel projectKey={key} />
      ) : (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Empty
            description={
              <span style={{ color: '#7e94b8' }}>Выберите проект из списка слева</span>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </div>
      )}
    </div>
  );
}
