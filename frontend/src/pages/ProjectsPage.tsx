import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';
import { PortfolioView } from '../components/projects/PortfolioView';
import type { ProjectListFiltersState } from '../types/projects';
import { useRegisterHelp } from '../contexts/HelpContext';
import { useSkin } from '../contexts/ThemeContext';
import projectsHelp from '../../../docs/help/projects.md?raw';
import { DARK_THEME } from '../utils/constants';
import PultProjectsLayout from '../skins/pult/pages/ProjectsLayout';

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_QUARTER = (Math.floor(new Date().getMonth() / 3) + 1) as 1 | 2 | 3 | 4;

/** Отборы и выбор проекта страницы «Проекты» — общие для раскладки Aurora и обложек. */
function useProjectsPage() {
  const navigate = useNavigate();
  const { key } = useParams<{ key?: string }>();
  useRegisterHelp('Проекты', projectsHelp);
  const [filters, setFilters] = useState<ProjectListFiltersState>({
    search: '',
    statusCategory: '',
    category: '',
    year: CURRENT_YEAR,
    quarter: CURRENT_QUARTER,
  });

  const handleSelect = (selectedKey: string) => {
    // Повторный клик по выбранной карточке возвращает к сводке.
    if (selectedKey === key) {
      navigate('/projects');
      return;
    }
    navigate(`/projects/${encodeURIComponent(selectedKey)}`);
  };

  const showPortfolio = () => navigate('/projects');
  const openProject = (projectKey: string) => navigate(`/projects/${encodeURIComponent(projectKey)}`);

  return { selectedKey: key ?? null, filters, setFilters, handleSelect, showPortfolio, openProject };
}

export type ProjectsPageState = ReturnType<typeof useProjectsPage>;

export default function ProjectsPage() {
  const page = useProjectsPage();
  const skin = useSkin();
  if (skin === 'pult') return <PultProjectsLayout page={page} />;
  const { selectedKey: key, filters, setFilters, handleSelect, showPortfolio } = page;

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
        selectedKey={key}
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
