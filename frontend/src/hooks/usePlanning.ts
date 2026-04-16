import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getScenarios, deleteScenario, generateScenario } from '../api/planning';

export const useScenarios = (year?: string, quarter?: string) =>
  useQuery({
    queryKey: ['planning', 'scenarios', year, quarter],
    queryFn: () => getScenarios(year, quarter),
  });

export const useGenerateScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: generateScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};

export const useDeleteScenario = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['planning'] }),
  });
};
