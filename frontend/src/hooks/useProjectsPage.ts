import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import type { ProjectListFiltersState } from '../types/projects';
import { useRegisterHelp } from '../contexts/HelpContext';
import projectsHelp from '../../../docs/help/projects.md?raw';

/** Текущий год и квартал — отбор списка проектов по умолчанию. */
export function currentYearQuarter(now: Date = new Date()): { year: number; quarter: 1 | 2 | 3 | 4 } {
  return { year: now.getFullYear(), quarter: (Math.floor(now.getMonth() / 3) + 1) as 1 | 2 | 3 | 4 };
}

/**
 * Отборы и переходы раздела «Проекты» — общие для раскладки Aurora и
 * раскладок скинов.
 */
export function useProjectsPage() {
  const navigate = useNavigate();
  const { key } = useParams<{ key?: string }>();
  useRegisterHelp('Проекты', projectsHelp);
  const [filters, setFilters] = useState<ProjectListFiltersState>(() => {
    const { year, quarter } = currentYearQuarter();
    return { search: '', statusCategory: '', category: '', year, quarter };
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

  return { projectKey: key ?? null, filters, setFilters, handleSelect, showPortfolio };
}

export type ProjectsPageState = ReturnType<typeof useProjectsPage>;
