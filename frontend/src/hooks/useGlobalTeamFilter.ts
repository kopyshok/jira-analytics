import { createContext, useContext } from 'react';

export type GlobalTeamFilterCtx = {
  selectedTeams: string[];
  /** Группы внутри выбранных команд. Пусто — команда берётся целиком. */
  selectedSubgroups: string[];
  setSelectedTeams: (teams: string[], subgroups?: string[]) => Promise<void>;
  saving: boolean;
  queryParams: { teams?: string; subgroups?: string };
};

export const GlobalTeamFilterContext = createContext<GlobalTeamFilterCtx | null>(null);

export function useGlobalTeamFilter(): GlobalTeamFilterCtx {
  const ctx = useContext(GlobalTeamFilterContext);
  if (!ctx) throw new Error('useGlobalTeamFilter must be used inside GlobalTeamFilterProvider');
  return ctx;
}
