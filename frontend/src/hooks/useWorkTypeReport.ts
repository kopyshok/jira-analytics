import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import { workTypeReportApi, type GetReportParams } from '../api/workTypeReport';
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

function invalidateAfterCandidate(
  qc: ReturnType<typeof useQueryClient>,
) {
  qc.invalidateQueries({ queryKey: ['theme-list'] });
  qc.invalidateQueries({ queryKey: ['work-type-report'] });
}

export function useAcceptCandidate() {
  const qc = useQueryClient();
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
