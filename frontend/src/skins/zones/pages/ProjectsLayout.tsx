import './projects.css';
import { ProjectsList } from '../../../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../../../components/projects/ProjectDetailPanel';
import { PortfolioView } from '../../../components/projects/PortfolioView';
import type { ProjectsPageState } from '../../../hooks/useProjectsPage';

/**
 * «Проекты» в скине «Цветовые зоны»: слева белая колонка-блок со списком
 * проектов, справа — сводка портфеля (итоги в полосе зоны) или карточка проекта.
 */
export default function ProjectsZonesLayout({ pj }: { pj: ProjectsPageState }) {
  const { projectKey, filters, setFilters, handleSelect, showPortfolio } = pj;
  return (
    <div className="zn-fit pz">
      <ProjectsList
        variant="zones"
        selectedKey={projectKey}
        onSelect={handleSelect}
        filters={filters}
        onFiltersChange={setFilters}
        onShowPortfolio={showPortfolio}
      />
      <div className="pz-right">
        {projectKey ? (
          <section className="zn-card pz-detail">
            <ProjectDetailPanel projectKey={projectKey} year={filters.year} quarter={filters.quarter} />
          </section>
        ) : (
          <PortfolioView variant="zones" filters={filters} />
        )}
      </div>
    </div>
  );
}
