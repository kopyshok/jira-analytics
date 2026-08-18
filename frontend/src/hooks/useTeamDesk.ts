import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  teamDeskApi,
  type DeskFilterPrefs, type DeskMode, type DeskSettings, type FlagCode,
} from '../api/teamDesk';

export function useDeskOverview(params: {
  teams: string[];
  developers: string[];
  mode: DeskMode;
  periodStart?: string;
  periodEnd?: string;
  showReviewed: boolean;
  showDoneSubtasks: boolean;
}) {
  const period = params.mode === 'period';
  return useQuery({
    queryKey: ['team-desk', 'overview', params],
    queryFn: () =>
      teamDeskApi.overview({
        teams: params.teams.join(',') || undefined,
        developers: params.developers.join(',') || undefined,
        only_open: params.mode !== 'all',
        show_reviewed: params.showReviewed,
        show_done_subtasks: params.showDoneSubtasks,
        period_start: period ? params.periodStart : undefined,
        period_end: period ? params.periodEnd : undefined,
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

/** Выбор команд и людей хранится в профиле — он же на другом компьютере. */
export function useDeskFilter() {
  return useQuery({
    queryKey: ['team-desk', 'filter'],
    queryFn: () => teamDeskApi.filter(),
    staleTime: 60_000,
  });
}

export function useSaveDeskFilter() {
  return useMutation({
    mutationFn: (payload: DeskFilterPrefs) => teamDeskApi.saveFilter(payload),
  });
}

export function useSaveDeskSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DeskSettings) => teamDeskApi.saveSettings(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-desk'] }),
  });
}

/** Дневная норма «резиновой» задачи; null снимает признак. */
export function useSaveDailyRate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { issueId: string; hours: number | null }) =>
      teamDeskApi.saveDailyRate(vars.issueId, vars.hours),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-desk', 'overview'] }),
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
