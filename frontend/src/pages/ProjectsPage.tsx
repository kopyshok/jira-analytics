import { useNavigate, useParams } from 'react-router';
import { Empty } from 'antd';
import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';
import { DARK_THEME } from '../utils/constants';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { key } = useParams<{ key?: string }>();

  const handleSelect = (selectedKey: string) => {
    navigate(`/projects/${encodeURIComponent(selectedKey)}`);
  };

  return (
    <div
      className="projects-master-detail"
      style={{
        display: 'flex',
        height: 'calc(100vh - 64px)',
        background: DARK_THEME.pageBg,
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
              <span style={{ color: DARK_THEME.textMuted }}>Выберите проект из списка слева</span>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </div>
      )}
    </div>
  );
}
