import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { notification } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { updateMyTeams } from '../api/auth';
import { useAuth } from '../hooks/useAuth';
import { GlobalTeamFilterContext } from '../hooks/useGlobalTeamFilter';

export function GlobalTeamFilterProvider({ children }: { children: ReactNode }) {
  const { user, updateUser } = useAuth();
  const qc = useQueryClient();
  const [saving, setSaving] = useState(false);

  const selectedTeams = useMemo(() => user?.selected_teams ?? [], [user]);
  const selectedSubgroups = useMemo(() => user?.selected_subgroups ?? [], [user]);

  const setSelectedTeams = useCallback(async (next: string[], nextSubgroups: string[] = []) => {
    if (!user) return;
    const prev = user.selected_teams;
    const prevSubgroups = user.selected_subgroups ?? [];
    setSaving(true);
    updateUser({ ...user, selected_teams: next, selected_subgroups: nextSubgroups });
    try {
      const fresh = await updateMyTeams(next, nextSubgroups);
      updateUser(fresh);
      qc.invalidateQueries();
    } catch {
      updateUser({ ...user, selected_teams: prev, selected_subgroups: prevSubgroups });
      notification.error({ title: 'Не удалось сохранить выбор команд' });
    } finally {
      setSaving(false);
    }
  }, [user, updateUser, qc]);

  const queryParams = useMemo(
    () => ({
      ...(selectedTeams.length === 0 ? {} : { teams: selectedTeams.join(',') }),
      ...(selectedSubgroups.length === 0 ? {} : { subgroups: selectedSubgroups.join(',') }),
    }),
    [selectedTeams, selectedSubgroups],
  );

  const value = useMemo(
    () => ({ selectedTeams, selectedSubgroups, setSelectedTeams, saving, queryParams }),
    [selectedTeams, selectedSubgroups, setSelectedTeams, saving, queryParams],
  );

  return <GlobalTeamFilterContext.Provider value={value}>{children}</GlobalTeamFilterContext.Provider>;
}
