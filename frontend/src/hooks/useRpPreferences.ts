import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  getRpPreferences,
  patchRpPreferences,
  type RpPreferences,
} from '../api/resourcePlanning';

const DEFAULT_PREFS: RpPreferences = {
  hide_weekends: false,
  collapsed_initiative_ids: [],
  view_mode: null,
  show_relay: true,
};

const QUERY_KEY = ['rp-preferences'];

export function useRpPreferences() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: getRpPreferences,
    staleTime: 60_000,
  });

  const mutation = useMutation({
    mutationFn: (patch: Partial<RpPreferences>) => patchRpPreferences(patch),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: QUERY_KEY });
      const prev = qc.getQueryData<RpPreferences>(QUERY_KEY);
      if (prev) {
        qc.setQueryData<RpPreferences>(QUERY_KEY, { ...prev, ...patch });
      }
      return { prev };
    },
    onError: (_err, _patch, ctx) => {
      if (ctx?.prev) qc.setQueryData(QUERY_KEY, ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });

  return {
    prefs: query.data ?? DEFAULT_PREFS,
    isLoading: query.isLoading,
    patch: mutation.mutate,
  };
}
