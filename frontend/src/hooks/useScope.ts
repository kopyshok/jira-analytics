import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getScopeProjects, addScopeProject, removeScopeProject, getScopeRoots, addScopeRoot, removeScopeRoot, getOverrides, addOverride, removeOverride } from '../api/scope';

export const useScopeProjects = () =>
  useQuery({ queryKey: ['scope', 'projects'], queryFn: getScopeProjects });

export const useAddScopeProject = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: addScopeProject, onSuccess: () => qc.invalidateQueries({ queryKey: ['scope', 'projects'] }) });
};

export const useRemoveScopeProject = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: removeScopeProject, onSuccess: () => qc.invalidateQueries({ queryKey: ['scope', 'projects'] }) });
};

export const useScopeRoots = () =>
  useQuery({ queryKey: ['scope', 'roots'], queryFn: getScopeRoots });

export const useAddScopeRoot = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: addScopeRoot, onSuccess: () => qc.invalidateQueries({ queryKey: ['scope', 'roots'] }) });
};

export const useRemoveScopeRoot = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: removeScopeRoot, onSuccess: () => qc.invalidateQueries({ queryKey: ['scope', 'roots'] }) });
};

export const useOverrides = () =>
  useQuery({ queryKey: ['scope', 'overrides'], queryFn: getOverrides });

export const useAddOverride = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: addOverride, onSuccess: () => qc.invalidateQueries({ queryKey: ['scope', 'overrides'] }) });
};

export const useRemoveOverride = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: removeOverride, onSuccess: () => qc.invalidateQueries({ queryKey: ['scope', 'overrides'] }) });
};
