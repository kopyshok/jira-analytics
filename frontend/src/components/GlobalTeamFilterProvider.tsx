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

  const setSelectedTeams = useCallback(async (next: string[]) => {
    if (!user) return;
    const prev = user.selected_teams;
    setSaving(true);
    updateUser({ ...user, selected_teams: next });
    try {
      const fresh = await updateMyTeams(next);
      updateUser(fresh);
      qc.invalidateQueries();
    } catch {
      updateUser({ ...user, selected_teams: prev });
      notification.error({ message: 'Не удалось сохранить выбор команд' });
    } finally {
      setSaving(false);
    }
  }, [user, updateUser, qc]);

  const queryParams = useMemo(
    () => (selectedTeams.length === 0 ? {} : { teams: selectedTeams.join(',') }),
    [selectedTeams],
  );

  const value = useMemo(
    () => ({ selectedTeams, setSelectedTeams, saving, queryParams }),
    [selectedTeams, setSelectedTeams, saving, queryParams],
  );

  return <GlobalTeamFilterContext.Provider value={value}>{children}</GlobalTeamFilterContext.Provider>;
}
