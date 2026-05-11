import { useNavigate, useParams } from 'react-router';
import { Empty, Row, Col } from 'antd';
import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';
import { useThemeTokens } from '../hooks/useThemeTokens';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { key } = useParams<{ key?: string }>();
  const t = useThemeTokens();

  const handleSelect = (selectedKey: string) => {
    navigate(`/projects/${encodeURIComponent(selectedKey)}`);
  };

  return (
    <div
      className="projects-master-detail"
      style={{
        minHeight: 'calc(100vh - 64px)',
        background: t.surface.page,
      }}
    >
      <Row gutter={0} wrap>
        <Col xs={24} md={8} lg={6} style={{ borderRight: `1px solid ${t.border.default}` }}>
          <ProjectsList selectedKey={key ?? null} onSelect={handleSelect} />
        </Col>
        <Col xs={24} md={16} lg={18}>
          {key ? (
            <ProjectDetailPanel projectKey={key} />
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 400 }}>
              <Empty
                description={
                  <span style={{ color: t.text.muted }}>Выберите проект из списка слева</span>
                }
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </div>
          )}
        </Col>
      </Row>
    </div>
  );
}
