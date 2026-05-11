import { useCallback, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import { workTypeReportApi, type GetReportParams, type BuildEvent } from '../api/workTypeReport';
import type {
  CandidateAcceptRequest,
  CandidateMergeRequest,
  CandidateIgnoreRequest,
  ManualClassifyRequest,
} from '../types/workTypeReport';

function reportKey(params: GetReportParams) {
  const teamsCsv = params.teams && params.teams.length > 0 ? params.teams.join(',') : '';
  return [
    'work-type-report',
    params.work_type_id,
    params.year,
    params.quarter,
    params.month ?? null,
    teamsCsv,
  ] as const;
}

/**
 * GET cached snapshot. Triggers build on first call (backend get_or_build).
 * Pass `enabled: false` to defer until params are ready.
 */
export function useWorkTypeReport(
  params: GetReportParams,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: reportKey(params),
    queryFn: ({ signal }) => workTypeReportApi.get(params, signal),
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
  });
}

/** POST force-refresh — always builds a new snapshot. */
export function useBuildWorkTypeReport() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (body: Parameters<typeof workTypeReportApi.build>[0]) =>
      workTypeReportApi.build(body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['work-type-report', data.work_type_id] });
      message.success('Отчёт обновлён');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось построить отчёт: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export interface BuildStreamState {
  phase: 'scope' | 'map' | 'cluster' | 'reduce' | 'save' | null;
  current: number;
  total: number;
  item_key: string | null;
  isRunning: boolean;
  error: string | null;
}

const INITIAL_STATE: BuildStreamState = {
  phase: null,
  current: 0,
  total: 0,
  item_key: null,
  isRunning: false,
  error: null,
};

/** SSE-streamed build. Returns start/cancel and live progress state. */
export function useBuildWorkTypeReportStream() {
  const qc = useQueryClient();
  const [state, setState] = useState<BuildStreamState>(INITIAL_STATE);
  const ctrlRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    ctrlRef.current?.abort();
    setState((s) => ({ ...s, isRunning: false }));
  }, []);

  const start = useCallback(
    async (
      body: Parameters<typeof workTypeReportApi.buildStream>[0],
      onDone?: () => void,
    ) => {
      ctrlRef.current?.abort();
      const ctrl = new AbortController();
      ctrlRef.current = ctrl;
      setState({ ...INITIAL_STATE, isRunning: true });

      const handleEvent = (e: BuildEvent) => {
        if (e.type === 'phase_start') {
          setState((s) => ({
            ...s,
            phase: e.phase,
            current: 0,
            total: e.total ?? 0,
            item_key: null,
          }));
        } else if (e.type === 'progress') {
          setState((s) => ({
            ...s,
            current: e.current,
            total: e.total,
            item_key: e.item_key ?? null,
          }));
        } else if (e.type === 'phase_done') {
          // phase stays until next phase_start
        } else if (e.type === 'done') {
          setState({ ...INITIAL_STATE, isRunning: false });
          qc.invalidateQueries({ queryKey: ['work-type-report', e.work_type_id] });
          onDone?.();
        } else if (e.type === 'cancelled') {
          setState((s) => ({ ...s, isRunning: false }));
        } else if (e.type === 'error') {
          setState((s) => ({ ...s, isRunning: false, error: e.detail }));
        }
      };

      try {
        await workTypeReportApi.buildStream(body, handleEvent, ctrl.signal);
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          setState((s) => ({
            ...s,
            isRunning: false,
            error: (e as Error).message ?? 'Ошибка',
          }));
        } else {
          setState((s) => ({ ...s, isRunning: false }));
        }
      }
    },
    [qc],
  );

  return { start, cancel, state };
}

function invalidateAfterCandidate(
  qc: ReturnType<typeof useQueryClient>,
) {
  qc.invalidateQueries({ queryKey: ['theme-list'] });
  qc.invalidateQueries({ queryKey: ['work-type-report'] });
}

export function useAcceptCandidate() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (body: CandidateAcceptRequest) =>
      workTypeReportApi.acceptCandidate(body),
    onSuccess: () => {
      invalidateAfterCandidate(qc);
      message.success('Кандидат принят — тема добавлена в словарь');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось принять кандидата: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useMergeCandidate() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (body: CandidateMergeRequest) =>
      workTypeReportApi.mergeCandidate(body),
    onSuccess: () => {
      invalidateAfterCandidate(qc);
      message.success('Кандидат объединён с темой');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось объединить кандидата: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useIgnoreCandidate() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (body: CandidateIgnoreRequest) =>
      workTypeReportApi.ignoreCandidate(body),
    onSuccess: () => {
      invalidateAfterCandidate(qc);
      message.success('Кандидат отклонён');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось отклонить кандидата: ${err?.message ?? 'Ошибка'}`);
    },
  });
}

export function useManualClassify() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  return useMutation({
    mutationFn: (body: ManualClassifyRequest) =>
      workTypeReportApi.manualClassify(body),
    onSuccess: () => {
      invalidateAfterCandidate(qc);
      message.success('Классификация сохранена');
    },
    onError: (e: unknown) => {
      const err = e as { message?: string };
      message.error(`Не удалось сохранить классификацию: ${err?.message ?? 'Ошибка'}`);
    },
  });
}
