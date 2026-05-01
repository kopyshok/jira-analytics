import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

interface WorkTypeItem {
  id: string;
  code: string;
  label: string;
  is_active: boolean;
  sort_order: number;
}

const listWorkTypes = () => api.get<WorkTypeItem[]>('/mandatory-work-types', { is_active: 'true' });

export function useMandatoryWorkTypes() {
  return useQuery({
    queryKey: ['mandatory-work-types'],
    queryFn: listWorkTypes,
    staleTime: 60_000,
  });
}
