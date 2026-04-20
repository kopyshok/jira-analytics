import { createContext, useContext } from 'react';

export const NO_TEAM_VALUE = '__none__';

export type CapacityFilterCtx = {
  selectedTeams: string[];
  setSelectedTeams: (teams: string[]) => void;
  hydrated: boolean;
  matchesTeam: (employeeId: string) => boolean;
};

export const CapacityFilterContext = createContext<CapacityFilterCtx | null>(null);

export function useCapacityFilter(): CapacityFilterCtx {
  const ctx = useContext(CapacityFilterContext);
  if (!ctx) throw new Error('useCapacityFilter must be used inside CapacityFilterProvider');
  return ctx;
}
