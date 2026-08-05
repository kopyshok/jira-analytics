import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { teamDeskApi, type DeskSettings, type FlagCode } from '../api/teamDesk';

export function useDeskOverview(params: {
  teams: string[];
  developers: string[];
  onlyOpen: boolean;
  showReviewed: boolean;
}) {
  return useQuery({
    queryKey: ['team-desk', 'overview', params],
    queryFn: () =>
      teamDeskApi.overview({
        teams: params.teams.join(',') || undefined,
        developers: params.developers.join(',') || undefined,
        only_open: params.onlyOpen,
        show_reviewed: params.showReviewed,
      }),
    enabled: params.teams.length > 0 || params.developers.length > 0,
  });
}

export function useDeskSettings() {
  return useQuery({
    queryKey: ['team-desk', 'settings'],
    queryFn: () => teamDeskApi.settings(),
  });
}

export function useSaveDeskSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DeskSettings) => teamDeskApi.saveSettings(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-desk'] }),
  });
}

export function useMarkFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      issueId: string;
      flag: FlagCode;
      signature: string;
      comment?: string;
    }) =>
      teamDeskApi.mark(vars.issueId, {
        flag: vars.flag,
        signature: vars.signature,
        comment: vars.comment,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-desk', 'overview'] }),
  });
}

export function useUnmarkFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { issueId: string; flag: FlagCode }) =>
      teamDeskApi.unmark(vars.issueId, vars.flag),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-desk', 'overview'] }),
  });
}
