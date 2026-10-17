import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';
import { PortfolioView } from '../components/projects/PortfolioView';
import { DARK_THEME } from '../utils/constants';
import { useSkin } from '../contexts/ThemeContext';
import { useProjectsPage, type ProjectsPageModel } from '../hooks/useProjectsPage';
import SwissProjectsLayout from '../skins/swiss/pages/ProjectsLayout';

/** Раскладка Aurora: список проектов слева, справа сводка портфеля или карточка проекта. */
function AuroraProjectsLayout({ vm }: { vm: ProjectsPageModel }) {
  const { key, filters, setFilters, handleSelect, showPortfolio } = vm;
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
  const vm = useProjectsPage();
  const skin = useSkin();
  return skin === 'swiss' ? <SwissProjectsLayout vm={vm} /> : <AuroraProjectsLayout vm={vm} />;
}
