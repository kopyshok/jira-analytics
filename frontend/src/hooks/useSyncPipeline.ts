import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { runPipelineStream, type PipelineEvent, type PipelineMode } from '../api/syncPipeline';

export type PipelineStageState = {
  stage: string;
  status: 'running' | 'done' | 'failed' | 'skipped';
  counts?: Record<string, number>;
  error?: string;
};

export type PipelineRunState = {
  /** null — pipeline не запущен */
  runId: string | null;
  status: 'idle' | 'running' | 'done' | 'failed' | 'cancelled';
  stages: PipelineStageState[];
  error: string | null;
};

const IDLE: PipelineRunState = {
  runId: null,
  status: 'idle',
  stages: [],
  error: null,
};

/**
 * Хук для запуска sync pipeline через SSE.
 * Управляет состоянием (стадии, статус, прерывание).
 */
export function useSyncPipeline() {
  const qc = useQueryClient();
  const abortRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<PipelineRunState>(IDLE);

  const start = useCallback(
    async (mode: PipelineMode, team?: string) => {
      // Отменить предыдущий
      abortRef.current?.abort();
      const ctl = new AbortController();
      abortRef.current = ctl;

      setState({ runId: null, status: 'running', stages: [], error: null });

      const handleEvent = (event: PipelineEvent) => {
        setState((prev) => {
          switch (event.type) {
            case 'sync_started':
              return { ...prev, runId: event.run_id };
            case 'stage_start':
              return {
                ...prev,
                stages: [
                  ...prev.stages.filter((s) => s.stage !== event.stage),
                  { stage: event.stage, status: 'running' },
                ],
              };
            case 'stage_done':
              return {
                ...prev,
                stages: prev.stages.map((s) =>
                  s.stage === event.stage
                    ? { ...s, status: 'done', counts: event.counts }
                    : s,
                ),
              };
            case 'stage_failed':
              return {
                ...prev,
                stages: prev.stages.map((s) =>
                  s.stage === event.stage
                    ? { ...s, status: 'failed', error: event.error }
                    : s,
                ),
              };
            default:
              return prev;
          }
        });
      };

      try {
        const result = await runPipelineStream({ mode, team }, handleEvent, ctl.signal);
        setState((prev) => ({
          ...prev,
          runId: result.run_id,
          status: result.status === 'ok' || result.status === 'partial' ? 'done' : 'failed',
        }));
        qc.invalidateQueries({ queryKey: ['sync', 'runs'] });
        qc.invalidateQueries({ queryKey: ['sync', 'status'] });
      } catch (e) {
        if ((e as Error).name === 'AbortError') {
          setState((prev) => ({ ...prev, status: 'cancelled' }));
        } else {
          setState((prev) => ({
            ...prev,
            status: 'failed',
            error: (e as Error).message,
          }));
        }
      }
    },
    [qc],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    setState(IDLE);
  }, []);

  return { state, start, cancel, reset };
}
