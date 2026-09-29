import { api } from './client';
import type { SubgroupShareItem, SubgroupShareRecord } from '../types/api';

export type Subgroup = { id: string; name: string; sort_order: number };
export type TeamRegistryRow = { name: string; has_subgroups: boolean; subgroups: Subgroup[] };

const enc = encodeURIComponent;

export const getTeamRegistry = () => api.get<TeamRegistryRow[]>('/teams/registry');

export const setTeamHasSubgroups = (name: string, has_subgroups: boolean) =>
  api.patch<TeamRegistryRow>(`/teams/registry/${enc(name)}`, { has_subgroups });

export const addSubgroup = (team: string, name: string) =>
  api.post<Subgroup>(`/teams/registry/${enc(team)}/subgroups`, { name });

export const renameSubgroup = (id: string, name: string) =>
  api.patch<Subgroup>(`/teams/subgroups/${id}`, { name });

export const deleteSubgroup = (id: string) => api.del<void>(`/teams/subgroups/${id}`);

export const setEmployeeSubgroup = (
  employeeId: string,
  team: string,
  subgroupId: string | null,
) => api.put<void>(`/teams/employees/${employeeId}/subgroup`, { team, subgroup_id: subgroupId });

export const getSubgroupShares = (employeeId: string, team: string) =>
  api.get<SubgroupShareRecord[]>(`/teams/employees/${employeeId}/subgroup-shares`, { team });

export const putSubgroupShare = (
  employeeId: string,
  body: { team: string; valid_from: string | null; shares: SubgroupShareItem[] },
) => api.put<SubgroupShareRecord[]>(`/teams/employees/${employeeId}/subgroup-shares`, body);

export const deleteSubgroupShare = (employeeId: string, team: string, validFrom: string | null) =>
  api.del<SubgroupShareRecord[]>(
    `/teams/employees/${employeeId}/subgroup-shares?team=${enc(team)}`
      + (validFrom ? `&valid_from=${validFrom}` : ''),
  );
