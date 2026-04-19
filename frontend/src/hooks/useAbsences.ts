import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAbsences, addAbsence, removeAbsence } from '../api/absences';

const KEY = ['capacity', 'absences'];

export const useAbsences = () =>
  useQuery({ queryKey: KEY, queryFn: () => getAbsences() });

export const useAddAbsence = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: addAbsence,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }),
  });
};

export const useRemoveAbsence = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: removeAbsence,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['capacity'] }),
  });
};
