import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export interface AppearanceSettings {
  phase_colors: { analyst: string; dev: string; qa: string; opo: string };
  initiative_bracket_color: string;
  initiative_fill_intensity: 'soft' | 'medium' | 'dense';
  animation_speed_seconds: number;
  hours_balance_lag_days: number;
}

export const APPEARANCE_QUERY_KEY = ['appearance'] as const;

export const fetchAppearance = (): Promise<AppearanceSettings> =>
  api.get<AppearanceSettings>('/users/me/appearance');

export const updateAppearance = (s: AppearanceSettings): Promise<AppearanceSettings> =>
  api.put<AppearanceSettings>('/users/me/appearance', s);

export function useAppearance() {
  return useQuery({
    queryKey: APPEARANCE_QUERY_KEY,
    queryFn: fetchAppearance,
    staleTime: 60_000,
  });
}

export function useUpdateAppearance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updateAppearance,
    onSuccess: (data) => {
      queryClient.setQueryData(APPEARANCE_QUERY_KEY, data);
    },
  });
}
