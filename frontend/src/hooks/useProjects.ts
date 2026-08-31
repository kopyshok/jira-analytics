import { useQuery } from '@tanstack/react-query';
import { projectsApi } from '../api/projects';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';

export function useProjectsList(filters: {
  category?: string;
  status_category?: string;
  search?: string;
  year?: number;
  quarter?: number;
}) {
  const { queryParams } = useGlobalTeamFilter();
  const teams = queryParams.teams;
  const subgroups = queryParams.subgroups;
  return useQuery({
    queryKey: ['projects', teams, subgroups, filters],
    queryFn: ({ signal }) => projectsApi.list({
      teams,
      subgroups,
      ...filters,
      year: filters.year !== undefined ? String(filters.year) : undefined,
      quarter: filters.quarter !== undefined ? String(filters.quarter) : undefined,
    }, signal),
    staleTime: 30_000,
  });
}

export function useProjectDetail(key: string | null) {
  return useQuery({
    queryKey: ['project-detail', key],
    queryFn: ({ signal }) => projectsApi.detail(key!, signal),
    enabled: !!key,
    staleTime: 30_000,
  });
}

export function useProjectPlan(key: string | null, year: number, quarter: number) {
  return useQuery({
    queryKey: ['project-plan', key, year, quarter],
    queryFn: ({ signal }) =>
      projectsApi.plan(key!, { year: String(year), quarter: String(quarter) }, signal),
    enabled: !!key,
    staleTime: 30_000,
  });
}

export function usePortfolio(filters: {
  category?: string;
  status_category?: string;
  search?: string;
  year: number;
  quarter: number;
}) {
  const { queryParams } = useGlobalTeamFilter();
  const teams = queryParams.teams;
  const subgroups = queryParams.subgroups;
  return useQuery({
    queryKey: ['projects-portfolio', teams, subgroups, filters],
    queryFn: ({ signal }) => projectsApi.portfolio({
      teams,
      subgroups,
      category: filters.category,
      status_category: filters.status_category,
      search: filters.search,
      year: String(filters.year),
      quarter: String(filters.quarter),
    }, signal),
    staleTime: 30_000,
  });
}
