import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useGenericSetting, useSaveGenericSetting } from '../../hooks/useSettings';
import { FactFilterContext } from '../../hooks/useFactFilter';

const KEY_TEAMS = 'ui_fact_filter_teams';
const KEY_EMPS = 'ui_fact_filter_scope_employees';
const KEY_ISSUES = 'ui_fact_filter_scope_issues';

export default function FactFilterProvider({ children }: { children: ReactNode }) {
  const storedTeams = useGenericSetting(KEY_TEAMS);
  const storedEmps = useGenericSetting(KEY_EMPS);
  const storedIssues = useGenericSetting(KEY_ISSUES);
  const save = useSaveGenericSetting();

  const [selectedTeams, setSelectedTeamsState] = useState<string[]>([]);
  const [matchEmployees, setMatchEmployeesState] = useState(true);
  const [matchIssues, setMatchIssuesState] = useState(true);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated) return;
    if (storedTeams.data === undefined || storedEmps.data === undefined || storedIssues.data === undefined) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedTeamsState((storedTeams.data?.value || '').split(',').filter(Boolean));
    setMatchEmployeesState(storedEmps.data?.value !== '0'); // default true
    setMatchIssuesState(storedIssues.data?.value !== '0');
    setHydrated(true);
  }, [hydrated, storedTeams.data, storedEmps.data, storedIssues.data]);

  const setSelectedTeams = useCallback((teams: string[]) => {
    setSelectedTeamsState(teams);
    save.mutate({ key: KEY_TEAMS, value: teams.join(',') });
  }, [save]);

  const setMatchEmployees = useCallback((v: boolean) => {
    if (!v && !matchIssues) return; // refuse: at least one must stay on
    setMatchEmployeesState(v);
    save.mutate({ key: KEY_EMPS, value: v ? '1' : '0' });
  }, [matchIssues, save]);

  const setMatchIssues = useCallback((v: boolean) => {
    if (!v && !matchEmployees) return;
    setMatchIssuesState(v);
    save.mutate({ key: KEY_ISSUES, value: v ? '1' : '0' });
  }, [matchEmployees, save]);

  const queryParams = useMemo(() => {
    if (selectedTeams.length === 0) return {};
    return {
      teams: selectedTeams.join(','),
      match_employees: matchEmployees,
      match_issues: matchIssues,
    };
  }, [selectedTeams, matchEmployees, matchIssues]);

  const value = useMemo(
    () => ({
      selectedTeams, setSelectedTeams,
      matchEmployees, setMatchEmployees,
      matchIssues, setMatchIssues,
      hydrated, queryParams,
    }),
    [selectedTeams, setSelectedTeams, matchEmployees, setMatchEmployees, matchIssues, setMatchIssues, hydrated, queryParams],
  );

  return <FactFilterContext.Provider value={value}>{children}</FactFilterContext.Provider>;
}
