import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  addSubgroup,
  deleteSubgroup,
  deleteSubgroupShare,
  getSubgroupShares,
  getTeamRegistry,
  getUngroupedEmployees,
  putSubgroupShare,
  renameSubgroup,
  setEmployeeSubgroup,
  setTeamHasSubgroups,
  type TeamRegistryRow,
} from '../api/teams';
import type { SubgroupShareItem } from '../types/api';

const KEY = ['teams', 'registry'] as const;

export const useTeamRegistry = () =>
  useQuery({ queryKey: KEY, queryFn: getTeamRegistry });

/** Команда из реестра по имени. Undefined — реестр ещё не загружен. */
export const useTeamRegistryRow = (team?: string | null): TeamRegistryRow | undefined => {
  const { data } = useTeamRegistry();
  if (!team) return undefined;
  return data?.find((t) => t.name === team);
};

export const useSetTeamHasSubgroups = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      setTeamHasSubgroups(name, enabled),
    // Признак меняет второй уровень фильтра в шапке и разрезы в разделах —
    // инвалидируем и плоский список команд.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
      qc.invalidateQueries({ queryKey: ['teams'] });
    },
  });
};

export const useAddSubgroup = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ team, name }: { team: string; name: string }) => addSubgroup(team, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
};

export const useRenameSubgroup = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameSubgroup(id, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
};

export const useDeleteSubgroup = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSubgroup(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
      qc.invalidateQueries({ queryKey: ['capacity'] });
    },
  });
};

export const useSetEmployeeSubgroup = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      employeeId,
      team,
      subgroupId,
    }: {
      employeeId: string;
      team: string;
      subgroupId: string | null;
    }) => setEmployeeSubgroup(employeeId, team, subgroupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
      // Группа сотрудника приезжает в составе команд сотрудника — без этого
      // селект в «Ресурсах» показывает старое значение до перезагрузки.
      qc.invalidateQueries({ queryKey: ['employees'] });
      qc.invalidateQueries({ queryKey: ['capacity'] });
      qc.invalidateQueries({ queryKey: ['planning'] });
      qc.invalidateQueries({ queryKey: ['teams', 'ungrouped'] });
    },
  });
};

export const useSubgroupShares = (employeeId: string | null, team: string | null) =>
  useQuery({
    queryKey: ['subgroup-shares', employeeId, team],
    queryFn: () => getSubgroupShares(employeeId!, team!),
    enabled: !!employeeId && !!team,
  });

/** Сотрудники без группы в квартале — плашка в «Ресурсах» и «Сценариях». */
export const useUngroupedEmployees = (teams: string[], year: number, quarter: number) =>
  useQuery({
    queryKey: ['teams', 'ungrouped', teams, year, quarter],
    queryFn: () => getUngroupedEmployees(teams, year, quarter),
  });

// Распределение меняет группу задач, ресурс сценария и витрины.
const invalidateShares = (qc: ReturnType<typeof useQueryClient>) => {
  qc.invalidateQueries({ queryKey: ['subgroup-shares'] });
  qc.invalidateQueries({ queryKey: ['employees'] });
  qc.invalidateQueries({ queryKey: ['employee', 'teams'] });
  qc.invalidateQueries({ queryKey: ['capacity'] });
  qc.invalidateQueries({ queryKey: ['planning'] });
  qc.invalidateQueries({ queryKey: ['gantt'] });
  qc.invalidateQueries({ queryKey: ['resource-plans'] });
  qc.invalidateQueries({ queryKey: ['dashboard', 'hours-balance'] });
  qc.invalidateQueries({ queryKey: ['teams', 'ungrouped'] });
};

export const usePutSubgroupShare = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { employeeId: string; team: string; valid_from: string | null; shares: SubgroupShareItem[] }) =>
      putSubgroupShare(v.employeeId, { team: v.team, valid_from: v.valid_from, shares: v.shares }),
    onSuccess: () => invalidateShares(qc),
  });
};

export const useDeleteSubgroupShare = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { employeeId: string; team: string; valid_from: string | null }) =>
      deleteSubgroupShare(v.employeeId, v.team, v.valid_from),
    onSuccess: () => invalidateShares(qc),
  });
};
