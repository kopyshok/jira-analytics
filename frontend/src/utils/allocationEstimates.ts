import type { AllocationResponse } from '../types/api';

/** Зеркало backend `effective_estimate_hours`:
 *  если хоть одно override_estimate_*_hours не null → берём 4 цифры из override
 *  (null → 0); иначе — estimate_*_hours от BacklogItem. */
export function effectiveEstimate(a: AllocationResponse): {
  analyst: number;
  dev: number;
  qa: number;
  opo: number;
} {
  const hasOverride =
    a.override_estimate_analyst_hours !== null ||
    a.override_estimate_dev_hours !== null ||
    a.override_estimate_qa_hours !== null ||
    a.override_estimate_opo_hours !== null;
  if (hasOverride) {
    return {
      analyst: a.override_estimate_analyst_hours ?? 0,
      dev: a.override_estimate_dev_hours ?? 0,
      qa: a.override_estimate_qa_hours ?? 0,
      opo: a.override_estimate_opo_hours ?? 0,
    };
  }
  return {
    analyst: a.estimate_analyst_hours ?? 0,
    dev: a.estimate_dev_hours ?? 0,
    qa: a.estimate_qa_hours ?? 0,
    opo: a.estimate_opo_hours ?? 0,
  };
}
