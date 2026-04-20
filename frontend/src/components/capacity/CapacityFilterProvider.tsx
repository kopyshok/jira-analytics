import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useEmployees } from '../../hooks/useCapacity';
import { useGenericSetting, useSaveGenericSetting } from '../../hooks/useSettings';
import { CapacityFilterContext, NO_TEAM_VALUE } from '../../hooks/useCapacityFilter';

const STORAGE_KEY = 'ui_capacity_team_filter_teams';

export default function CapacityFilterProvider({ children }: { children: ReactNode }) {
  const stored = useGenericSetting(STORAGE_KEY);
  const save = useSaveGenericSetting();
  const [selectedTeams, setSelectedTeamsState] = useState<string[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated || stored.data === undefined) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedTeamsState((stored.data?.value || '').split(',').filter(Boolean));
    setHydrated(true);
  }, [hydrated, stored.data]);

  const setSelectedTeams = useCallback((teams: string[]) => {
    setSelectedTeamsState(teams);
    save.mutate({ key: STORAGE_KEY, value: teams.join(',') });
  }, [save]);

  const empsWithTeams = useEmployees({ withTeams: true });
  const employeeTeamMap = useMemo(() => {
    const m = new Map<string, string[]>();
    (empsWithTeams.data ?? []).forEach(e => {
      m.set(e.id, (e.teams ?? []).map(t => t.team));
    });
    return m;
  }, [empsWithTeams.data]);

  const matchesTeam = useCallback((employeeId: string): boolean => {
    if (selectedTeams.length === 0) return true;
    const teams = employeeTeamMap.get(employeeId) ?? [];
    if (teams.length === 0) return selectedTeams.includes(NO_TEAM_VALUE);
    return teams.some(t => selectedTeams.includes(t));
  }, [selectedTeams, employeeTeamMap]);

  const value = useMemo(
    () => ({ selectedTeams, setSelectedTeams, hydrated, matchesTeam }),
    [selectedTeams, setSelectedTeams, hydrated, matchesTeam],
  );

  return <CapacityFilterContext.Provider value={value}>{children}</CapacityFilterContext.Provider>;
}
