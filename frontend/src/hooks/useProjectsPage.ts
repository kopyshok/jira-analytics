import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import type { ProjectListFiltersState } from '../types/projects';
import { useRegisterHelp } from '../contexts/HelpContext';
import projectsHelp from '../../../docs/help/projects.md?raw';
import { usePortfolio } from './useProjects';

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_QUARTER = (Math.floor(new Date().getMonth() / 3) + 1) as 1 | 2 | 3 | 4;

/**
 * Отбор, выбранный проект и сводка портфеля страницы «Проекты» — общие для
 * всех раскладок (Aurora и обложки). Раскладки только рисуют.
 */
export function useProjectsPage() {
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

  return { key, filters, setFilters, handleSelect, showPortfolio, openProject };
}

/** Сводка портфеля по текущему отбору — тот же запрос, что у PortfolioView. */
export function usePortfolioForFilters(filters: ProjectListFiltersState) {
  return usePortfolio({
    search: filters.search || undefined,
    status_category: filters.statusCategory || undefined,
    category: filters.category || undefined,
    year: filters.year,
    quarter: filters.quarter,
  });
}

export type ProjectsPageModel = ReturnType<typeof useProjectsPage>;
