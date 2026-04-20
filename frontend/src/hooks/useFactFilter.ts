import { createContext, useContext } from 'react';

export const NO_TEAM_VALUE = '__none__';

export type FactFilterCtx = {
  selectedTeams: string[];
  setSelectedTeams: (v: string[]) => void;
  matchEmployees: boolean;
  setMatchEmployees: (v: boolean) => void;
  matchIssues: boolean;
  setMatchIssues: (v: boolean) => void;
  hydrated: boolean;
  queryParams: {
    teams?: string;
    match_employees?: boolean;
    match_issues?: boolean;
  };
};

export const FactFilterContext = createContext<FactFilterCtx | null>(null);

export function useFactFilter(): FactFilterCtx {
  const ctx = useContext(FactFilterContext);
  if (!ctx) throw new Error('useFactFilter must be used inside FactFilterProvider');
  return ctx;
}
