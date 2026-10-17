import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';
import { PortfolioView } from '../components/projects/PortfolioView';
import { DARK_THEME } from '../utils/constants';
import { useSkin } from '../contexts/ThemeContext';
import { useProjectsPage, type ProjectsPageState } from '../hooks/useProjectsPage';
import ProjectsZonesLayout from '../skins/zones/pages/ProjectsLayout';

function ProjectsAuroraLayout({ pj }: { pj: ProjectsPageState }) {
  const { projectKey: key, filters, setFilters, handleSelect, showPortfolio } = pj;
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
      <ProjectsList
        selectedKey={key ?? null}
        onSelect={handleSelect}
        filters={filters}
        onFiltersChange={setFilters}
        onShowPortfolio={showPortfolio}
      />

      {key ? (
        <ProjectDetailPanel
          projectKey={key}
          year={filters.year}
          quarter={filters.quarter}
        />
      ) : (
        <PortfolioView filters={filters} />
      )}
    </div>
  );
}

export default function ProjectsPage() {
  const pj = useProjectsPage();
  const skin = useSkin();
  if (skin === 'zones') return <ProjectsZonesLayout pj={pj} />;
  return <ProjectsAuroraLayout pj={pj} />;
}
