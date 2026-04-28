import { createContext, useContext } from 'react';

export type GlobalTeamFilterCtx = {
  selectedTeams: string[];
  setSelectedTeams: (teams: string[]) => Promise<void>;
  saving: boolean;
  queryParams: { teams?: string };
};

export const GlobalTeamFilterContext = createContext<GlobalTeamFilterCtx | null>(null);

export function useGlobalTeamFilter(): GlobalTeamFilterCtx {
  const ctx = useContext(GlobalTeamFilterContext);
  if (!ctx) throw new Error('useGlobalTeamFilter must be used inside GlobalTeamFilterProvider');
  return ctx;
}
