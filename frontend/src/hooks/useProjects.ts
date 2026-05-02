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
  return useQuery({
    queryKey: ['projects', teams, filters],
    queryFn: ({ signal }) => projectsApi.list({
      teams,
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
