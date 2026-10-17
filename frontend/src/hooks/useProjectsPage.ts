import { useCallback, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import projectsHelp from '../../../docs/help/projects.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import { usePortfolio, useProjectsList } from './useProjects';
import type { ProjectListFiltersState } from '../types/projects';
import { projectYearOptions } from '../utils/projectsView';

const CURRENT_YEAR = new Date().getFullYear();
const CURRENT_QUARTER = (Math.floor(new Date().getMonth() / 3) + 1) as 1 | 2 | 3 | 4;

function sameFilters(a: ProjectListFiltersState, b: ProjectListFiltersState): boolean {
  return a.search === b.search
    && a.statusCategory === b.statusCategory
    && a.category === b.category
    && a.year === b.year
    && a.quarter === b.quarter;
}

/**
 * Данные, состояние и обработчики раздела «Проекты». Один источник для
 * раскладки Aurora и раскладок скинов: фильтры списка (год, квартал, поиск,
 * статус, категория), выбранный проект из адреса, список проектов и сводка
 * портфеля. Карточка выбранного проекта грузит свои данные сама — её обе
 * раскладки показывают целиком.
 */
export function useProjectsPage() {
  const navigate = useNavigate();
  const { key } = useParams<{ key?: string }>();
  useRegisterHelp('Проекты', projectsHelp);
  const [filters, setFiltersState] = useState<ProjectListFiltersState>({
    search: '',
    statusCategory: '',
    category: '',
    year: CURRENT_YEAR,
    quarter: CURRENT_QUARTER,
  });
  // Поиск с задержкой отдаёт то же значение после каждой отрисовки — без
  // сравнения страница перерисовывалась бы раз в 300 мс вхолостую.
  const setFilters = useCallback((next: ProjectListFiltersState) => {
    setFiltersState((prev) => (sameFilters(prev, next) ? prev : next));
  }, []);
  const patchFilters = useCallback((part: Partial<ProjectListFiltersState>) => {
    setFiltersState((prev) => {
      const next = { ...prev, ...part };
      return sameFilters(prev, next) ? prev : next;
    });
  }, []);

  const apiFilters = useMemo(() => ({
    search: filters.search || undefined,
    status_category: filters.statusCategory || undefined,
    category: filters.category || undefined,
    year: filters.year,
    quarter: filters.quarter,
  }), [filters]);
  const list = useProjectsList(apiFilters);
  const portfolio = usePortfolio(apiFilters, { enabled: !key });

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

  return {
    projectKey: key ?? null,
    filters,
    setFilters,
    patchFilters,
    yearOptions: projectYearOptions(CURRENT_YEAR),
    projects: list.data,
    listLoading: list.isLoading,
    portfolio: portfolio.data,
    portfolioLoading: portfolio.isLoading,
    handleSelect,
    showPortfolio,
    openProject,
  };
}

export type ProjectsPageState = ReturnType<typeof useProjectsPage>;
