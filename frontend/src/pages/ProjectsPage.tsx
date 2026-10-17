import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';
import { PortfolioView } from '../components/projects/PortfolioView';
import { DARK_THEME } from '../utils/constants';
import { useSkin } from '../contexts/ThemeContext';
import { useProjectsPage, type ProjectsPageState } from '../hooks/useProjectsPage';
import WarmProjectsLayout from '../skins/warm/pages/ProjectsLayout';

export default function ProjectsPage() {
  const state = useProjectsPage();
  const skin = useSkin();
  if (skin === 'warm') return <WarmProjectsLayout state={state} />;
  return <AuroraProjectsLayout state={state} />;
}

/** Раскладка Aurora (тёмная и светлая) — как была до выделения данных в хук. */
function AuroraProjectsLayout({ state }: { state: ProjectsPageState }) {
  const {
    projectKey: key, filters, setFilters, yearOptions,
    projects, listLoading, portfolio, portfolioLoading,
    handleSelect, showPortfolio, openProject,
  } = state;

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
        projects={projects}
        isLoading={listLoading}
        yearOptions={yearOptions}
      />

      {key ? (
        <ProjectDetailPanel
          projectKey={key}
          year={filters.year}
          quarter={filters.quarter}
        />
      ) : (
        <PortfolioView data={portfolio} isLoading={portfolioLoading} onOpenProject={openProject} />
      )}
    </div>
  );
}
